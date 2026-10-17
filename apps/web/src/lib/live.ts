/**
 * Browser live-voice client.
 *
 * Talks to `services/api` over a WebSocket brokered by a short-lived ticket, so
 * the browser never holds the Gemini key. It captures the microphone as PCM16
 * @ 16 kHz (via an AudioWorklet), plays model audio back as PCM16 @ 24 kHz with
 * a small jitter buffer, and supports barge-in by stopping scheduled playback
 * the moment the model reports an interruption.
 *
 * Reconnection is bounded and exponential: a dropped socket is retried a few
 * times, then the client reports an error rather than looping forever.
 */
import { apiSend } from "./api";

export type VoiceState =
  | "idle"
  | "connecting"
  | "listening"
  | "thinking"
  | "speaking"
  | "error";

export interface LiveTicket {
  ticket: string;
  expires_in: number;
  model: string;
  voice: string;
  voices: string[];
  input_rate: number;
  output_rate: number;
}

export interface LiveCallbacks {
  onState?: (state: VoiceState) => void;
  onInputLevel?: (level: number) => void;
  onOutputLevel?: (level: number) => void;
  /** `final` is true when a turn has completed and the text is settled. */
  onTranscript?: (role: "user" | "assistant", text: string, final: boolean) => void;
  onError?: (message: string) => void;
  onReady?: (info: { voices: string[]; voice: string }) => void;
}

export interface StartOptions {
  voice?: string;
  deviceId?: string;
}

const WORKLET_URL = "/worklets/capture.worklet.js";
const OUTPUT_RATE = 24000;
const MIN_LEAD_SECONDS = 0.08; // jitter buffer before the first scheduled frame
const MAX_RECONNECTS = 5;
const BASE_RECONNECT_MS = 500;
const MAX_RECONNECT_MS = 8000;

function wsBase(): string {
  const explicit = process.env.NEXT_PUBLIC_API_WS_URL;
  if (explicit) return explicit.replace(/\/+$/, "");
  const http = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (http) return http.replace(/^http/, "ws").replace(/\/+$/, "");
  if (process.env.NODE_ENV === "production") {
    throw new Error("NEXT_PUBLIC_API_WS_URL must be set for live voice in production.");
  }
  return "ws://localhost:8080";
}

function friendlyMediaError(err: unknown): string {
  const name = err instanceof DOMException ? err.name : "";
  switch (name) {
    case "NotAllowedError":
    case "SecurityError":
      return "Microphone permission was denied. Enable it in your browser settings and try again.";
    case "NotFoundError":
    case "OverconstrainedError":
      return "No microphone was found. Connect a device and try again.";
    case "NotReadableError":
      return "The microphone is in use by another application.";
    default:
      return err instanceof Error ? err.message : "Unable to access the microphone.";
  }
}

export class LiveVoiceClient {
  private callbacks: LiveCallbacks;
  private voice: string | undefined;
  private deviceId: string | undefined;

  private socket: WebSocket | null = null;
  private context: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private worklet: AudioWorkletNode | null = null;
  private sink: GainNode | null = null;

  private scheduledTime = 0;
  private activeSources = new Set<AudioBufferSourceNode>();
  private outLevel = 0;
  private levelTimer: number | null = null;

  private state: VoiceState = "idle";
  private muted = false;
  private stopped = false;
  private ready = false;
  private reconnects = 0;
  private inputTranscript = "";
  private outputTranscript = "";

  constructor(callbacks: LiveCallbacks = {}) {
    this.callbacks = callbacks;
  }

  get currentState(): VoiceState {
    return this.state;
  }

  private setState(state: VoiceState) {
    if (this.state === state) return;
    this.state = state;
    this.callbacks.onState?.(state);
  }

  /** Prompt for the microphone and open a live session. */
  async start(options: StartOptions = {}): Promise<void> {
    this.stopped = false;
    this.voice = options.voice;
    this.deviceId = options.deviceId;
    this.reconnects = 0;
    this.setState("connecting");
    try {
      await this.openCapture();
      await this.connect();
    } catch (err) {
      this.emitError(err instanceof Error ? err.message : String(err));
      await this.stop();
    }
  }

  async stop(): Promise<void> {
    this.stopped = true;
    this.ready = false;
    this.clearLevelTimer();
    this.stopPlayback();
    try {
      this.worklet?.port.postMessage({ type: "mute", value: true });
    } catch {
      /* worklet already gone */
    }
    this.source?.disconnect();
    this.worklet?.disconnect();
    this.sink?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    if (this.context && this.context.state !== "closed") {
      try {
        await this.context.close();
      } catch {
        /* ignore */
      }
    }
    this.context = null;
    this.source = null;
    this.worklet = null;
    this.sink = null;
    if (this.socket) {
      const s = this.socket;
      this.socket = null;
      try {
        s.close(1000, "client stopping");
      } catch {
        /* ignore */
      }
    }
    this.setState("idle");
  }

  setMuted(muted: boolean): void {
    this.muted = muted;
    try {
      this.worklet?.port.postMessage({ type: "mute", value: muted });
    } catch {
      /* ignore */
    }
  }

  sendText(text: string): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ type: "text", text }));
      this.setState("thinking");
    }
  }

  // ── Capture ────────────────────────────────────────────────────────────────

  private async openCapture(): Promise<void> {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("This browser does not support microphone capture.");
    }
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          deviceId: this.deviceId ? { exact: this.deviceId } : undefined,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
    } catch (err) {
      throw new Error(friendlyMediaError(err));
    }
    this.stream = stream;

    const AudioCtor = window.AudioContext;
    const context = new AudioCtor();
    if (context.state === "suspended") await context.resume();
    this.context = context;

    await context.audioWorklet.addModule(WORKLET_URL);
    const source = context.createMediaStreamSource(stream);
    const worklet = new AudioWorkletNode(context, "mark-liv-capture", {
      numberOfInputs: 1,
      numberOfOutputs: 1,
      processorOptions: { targetRate: 16000 },
    });
    // A zero-gain sink keeps the worklet pulling audio without echoing the mic
    // back to the speakers.
    const sink = context.createGain();
    sink.gain.value = 0;

    worklet.port.onmessage = (event: MessageEvent) => this.onWorkletMessage(event);
    source.connect(worklet);
    worklet.connect(sink);
    sink.connect(context.destination);

    this.source = source;
    this.worklet = worklet;
    this.sink = sink;
    this.startLevelTimer();
  }

  private onWorkletMessage(event: MessageEvent) {
    const msg = event.data as { type?: string; data?: ArrayBuffer; value?: number };
    if (msg.type === "pcm" && msg.data) {
      if (
        !this.muted &&
        this.socket?.readyState === WebSocket.OPEN &&
        this.ready
      ) {
        this.socket.send(msg.data);
      }
    } else if (msg.type === "level") {
      this.callbacks.onInputLevel?.(typeof msg.value === "number" ? msg.value : 0);
    }
  }

  // ── Session ──────────────────────────────────────────────────────────────

  private async fetchTicket(): Promise<LiveTicket> {
    return apiSend<LiveTicket>("live/ticket", "POST", { voice: this.voice ?? null });
  }

  private async connect(): Promise<void> {
    const info = await this.fetchTicket();
    this.callbacks.onReady?.({ voices: info.voices, voice: info.voice });

    const url = `${wsBase()}/live/session?ticket=${encodeURIComponent(info.ticket)}` +
      `&voice=${encodeURIComponent(info.voice)}`;
    const socket = new WebSocket(url);
    socket.binaryType = "arraybuffer";
    this.socket = socket;

    socket.onopen = () => {
      this.setState("listening");
    };
    socket.onmessage = (event) => this.onSocketMessage(event);
    socket.onerror = () => {
      /* the close handler drives recovery / reporting */
    };
    socket.onclose = (event) => this.onSocketClose(event);
  }

  private onSocketMessage(event: MessageEvent) {
    if (typeof event.data === "string") {
      this.onControl(event.data);
      return;
    }
    // Binary frame: model audio, PCM16 little-endian at OUTPUT_RATE.
    const buffer = event.data as ArrayBuffer;
    this.playPcm16(new Int16Array(buffer));
  }

  private onControl(raw: string) {
    let msg: { type?: string; text?: string; message?: string };
    try {
      msg = JSON.parse(raw);
    } catch {
      return;
    }
    switch (msg.type) {
      case "ready":
        this.ready = true;
        this.reconnects = 0;
        this.setState("listening");
        break;
      case "input_transcript":
        this.inputTranscript = this.appendTranscript(this.inputTranscript, msg.text ?? "");
        this.callbacks.onTranscript?.("user", this.inputTranscript, false);
        break;
      case "output_transcript":
        this.outputTranscript = this.appendTranscript(this.outputTranscript, msg.text ?? "");
        this.setState("speaking");
        this.callbacks.onTranscript?.("assistant", this.outputTranscript, false);
        break;
      case "turn_complete":
        if (this.inputTranscript.trim()) {
          this.callbacks.onTranscript?.("user", this.inputTranscript.trim(), true);
        }
        if (this.outputTranscript.trim()) {
          this.callbacks.onTranscript?.("assistant", this.outputTranscript.trim(), true);
        }
        this.inputTranscript = "";
        this.outputTranscript = "";
        if (!this.activeSources.size) this.setState("listening");
        break;
      case "interrupted":
        this.stopPlayback();
        this.setState("listening");
        break;
      case "error":
        this.emitError(msg.message ?? "The voice session reported an error.");
        break;
      default:
        break;
    }
  }

  private appendTranscript(current: string, addition: string): string {
    if (!addition) return current;
    return current ? `${current}${addition}` : addition;
  }

  private onSocketClose(event: CloseEvent) {
    this.ready = false;
    if (this.stopped) return;
    if (event.code === 4401 || event.code === 4429) {
      // Authorization / concurrency rejection: retrying with the same session
      // state would just fail again.
      this.emitError(
        event.code === 4429
          ? "Too many active voice sessions. Close another and try again."
          : "Your voice session expired. Please start again.",
      );
      this.setState("error");
      return;
    }
    void this.scheduleReconnect();
  }

  private async scheduleReconnect(): Promise<void> {
    if (this.stopped) return;
    if (this.reconnects >= MAX_RECONNECTS) {
      this.emitError("Lost connection to the voice service. Please try again.");
      this.setState("error");
      return;
    }
    this.reconnects += 1;
    const delay = Math.min(BASE_RECONNECT_MS * 2 ** (this.reconnects - 1), MAX_RECONNECT_MS);
    this.setState("connecting");
    await new Promise((resolve) => window.setTimeout(resolve, delay));
    if (this.stopped) return;
    try {
      await this.connect();
    } catch (err) {
      this.emitError(err instanceof Error ? err.message : String(err));
      void this.scheduleReconnect();
    }
  }

  // ── Playback ───────────────────────────────────────────────────────────────

  private playPcm16(samples: Int16Array) {
    const context = this.context;
    if (!context || samples.length === 0) return;

    const floats = new Float32Array(samples.length);
    let sum = 0;
    for (let i = 0; i < samples.length; i++) {
      const v = (samples[i] ?? 0) / 0x8000;
      floats[i] = v;
      sum += v * v;
    }
    const rms = Math.sqrt(sum / samples.length);
    this.outLevel = Math.max(this.outLevel, Math.min(1, rms * 3.5));

    const buffer = context.createBuffer(1, floats.length, OUTPUT_RATE);
    buffer.copyToChannel(floats, 0);

    const node = context.createBufferSource();
    node.buffer = buffer;
    node.connect(context.destination);

    const now = context.currentTime;
    if (this.scheduledTime < now + MIN_LEAD_SECONDS) {
      this.scheduledTime = now + MIN_LEAD_SECONDS;
    }
    node.start(this.scheduledTime);
    this.scheduledTime += buffer.duration;

    this.activeSources.add(node);
    node.onended = () => this.activeSources.delete(node);
    this.setState("speaking");
  }

  private stopPlayback() {
    for (const node of this.activeSources) {
      try {
        node.stop();
      } catch {
        /* already stopped */
      }
    }
    this.activeSources.clear();
    this.outLevel = 0;
    if (this.context) this.scheduledTime = this.context.currentTime;
  }

  // ── Levels ─────────────────────────────────────────────────────────────────

  private startLevelTimer() {
    this.clearLevelTimer();
    this.levelTimer = window.setInterval(() => {
      // Decay the output level so the visualizer settles between frames.
      this.outLevel *= 0.6;
      if (this.outLevel < 0.01) this.outLevel = 0;
      this.callbacks.onOutputLevel?.(this.outLevel);
    }, 80);
  }

  private clearLevelTimer() {
    if (this.levelTimer !== null) {
      window.clearInterval(this.levelTimer);
      this.levelTimer = null;
    }
  }

  private emitError(message: string) {
    this.callbacks.onError?.(message);
  }
}
