"use client";

import { Loader2, Mic, MicOff, PhoneOff, Send, Volume2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { Visualizer } from "@/components/voice/visualizer";
import { Button } from "@/components/ui/button";
import { LiveVoiceClient, type VoiceState } from "@/lib/live";
import { cn } from "@/lib/utils";

type Turn = { role: "user" | "assistant"; text: string };

const STATE_LABEL: Record<VoiceState, string> = {
  idle: "Ready when you are",
  connecting: "Connecting…",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
  error: "Connection problem",
};

const STATE_DOT: Record<VoiceState, string> = {
  idle: "bg-muted",
  connecting: "bg-accent animate-pulse",
  listening: "bg-primary animate-pulse",
  thinking: "bg-accent animate-pulse",
  speaking: "bg-primary-soft animate-pulse",
  error: "bg-danger",
};

export default function VoicePage() {
  const clientRef = useRef<LiveVoiceClient | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const [state, setState] = useState<VoiceState>("idle");
  const [inputLevel, setInputLevel] = useState(0);
  const [outputLevel, setOutputLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [live, setLive] = useState<Turn | null>(null);
  const [active, setActive] = useState(false);
  const [muted, setMuted] = useState(false);
  const [voices, setVoices] = useState<string[]>([]);
  const [voice, setVoice] = useState("");
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [deviceId, setDeviceId] = useState("");
  const [draft, setDraft] = useState("");

  const refreshDevices = useCallback(async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return;
    const all = await navigator.mediaDevices.enumerateDevices();
    setDevices(all.filter((d) => d.kind === "audioinput"));
  }, []);

  useEffect(() => {
    void refreshDevices();
    navigator.mediaDevices?.addEventListener?.("devicechange", refreshDevices);
    return () => {
      navigator.mediaDevices?.removeEventListener?.("devicechange", refreshDevices);
    };
  }, [refreshDevices]);

  useEffect(() => {
    clientRef.current = new LiveVoiceClient({
      onState: setState,
      onInputLevel: setInputLevel,
      onOutputLevel: setOutputLevel,
      onError: (message) => setError(message),
      onReady: ({ voices: v, voice: chosen }) => {
        setVoices(v);
        setVoice((current) => current || chosen);
      },
      onTranscript: (role, text, final) => {
        if (final) {
          if (text) setTurns((prev) => [...prev, { role, text }]);
          setLive(null);
        } else {
          setLive({ role, text });
        }
      },
    });
    const client = clientRef.current;
    return () => {
      void client.stop();
    };
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, live]);

  const start = useCallback(async () => {
    setError(null);
    setTurns([]);
    setLive(null);
    setActive(true);
    await clientRef.current?.start({ voice: voice || undefined, deviceId: deviceId || undefined });
    // Labels only become readable after a permission grant.
    void refreshDevices();
  }, [voice, deviceId, refreshDevices]);

  const stop = useCallback(async () => {
    await clientRef.current?.stop();
    setActive(false);
    setMuted(false);
  }, []);

  const toggleMute = useCallback(() => {
    setMuted((prev) => {
      clientRef.current?.setMuted(!prev);
      return !prev;
    });
  }, []);

  const sendText = useCallback(() => {
    const value = draft.trim();
    if (!value || !active) return;
    clientRef.current?.sendText(value);
    setTurns((prev) => [...prev, { role: "user", text: value }]);
    setDraft("");
  }, [draft, active]);

  const level = useMemo(() => Math.max(inputLevel, outputLevel), [inputLevel, outputLevel]);

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Voice assistant"
        description="Have a live, spoken conversation. Interrupt any time by talking."
      />

      <div className="grid flex-1 grid-cols-1 overflow-hidden lg:grid-cols-[1.1fr_1fr]">
        {/* Stage */}
        <div className="flex flex-col items-center justify-center gap-6 border-b border-border/60 p-8 lg:border-b-0 lg:border-r">
          <div className="relative aspect-square w-full max-w-sm">
            <Visualizer level={level} state={state} className="h-full w-full" />
            <div className="pointer-events-none absolute inset-0 grid place-items-center">
              <button
                type="button"
                onClick={active ? () => void stop() : () => void start()}
                className={cn(
                  "pointer-events-auto grid h-24 w-24 place-items-center rounded-full border transition-all",
                  active
                    ? "border-danger/60 bg-danger/10 text-danger shadow-panel hover:bg-danger/20"
                    : "border-primary/50 bg-primary/10 text-primary shadow-glow hover:bg-primary/20",
                )}
                aria-label={active ? "End conversation" : "Start conversation"}
              >
                {state === "connecting" ? (
                  <Loader2 className="h-8 w-8 animate-spin" />
                ) : active ? (
                  <PhoneOff className="h-8 w-8" />
                ) : (
                  <Mic className="h-8 w-8" />
                )}
              </button>
            </div>
          </div>

          <div className="flex items-center gap-2 text-sm">
            <span className={cn("h-2 w-2 rounded-full", STATE_DOT[state])} />
            <span className="font-medium text-slate-200">{STATE_LABEL[state]}</span>
          </div>

          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={toggleMute} disabled={!active}>
              {muted ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
              {muted ? "Unmute" : "Mute"}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => void stop()} disabled={!active}>
              <PhoneOff className="h-4 w-4" /> End
            </Button>
          </div>

          {error ? (
            <p className="max-w-sm rounded-lg border border-danger/40 bg-danger/10 px-4 py-2 text-center text-sm text-danger">
              {error}
            </p>
          ) : null}

          <div className="flex w-full max-w-sm flex-col gap-2">
            <label className="text-xs uppercase tracking-wider text-muted" htmlFor="mic">
              Microphone
            </label>
            <select
              id="mic"
              className="rounded-lg border border-border bg-surface/70 px-3 py-2 text-sm text-slate-100"
              value={deviceId}
              onChange={(e) => setDeviceId(e.target.value)}
              disabled={active}
            >
              <option value="">System default</option>
              {devices.map((d, i) => (
                <option key={d.deviceId || i} value={d.deviceId}>
                  {d.label || `Microphone ${i + 1}`}
                </option>
              ))}
            </select>

            <label className="text-xs uppercase tracking-wider text-muted" htmlFor="voice">
              Voice
            </label>
            <select
              id="voice"
              className="rounded-lg border border-border bg-surface/70 px-3 py-2 text-sm text-slate-100"
              value={voice}
              onChange={(e) => setVoice(e.target.value)}
              disabled={active || voices.length === 0}
            >
              {voices.length === 0 ? <option value="">Default</option> : null}
              {voices.map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
            <p className="text-xs text-muted">
              Voice and microphone changes apply the next time you start a conversation.
            </p>
          </div>
        </div>

        {/* Transcript + typed input */}
        <div className="flex min-h-0 flex-col">
          <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto p-6">
            {turns.length === 0 && !live ? (
              <div className="grid h-full place-items-center text-center">
                <p className="max-w-xs text-sm text-muted">
                  Press the microphone and speak. MARK LIV replies out loud; start talking again
                  to interrupt.
                </p>
              </div>
            ) : (
              <>
                {turns.map((turn, i) => (
                  <Bubble key={i} role={turn.role} text={turn.text} />
                ))}
                {live ? <Bubble role={live.role} text={live.text} live /> : null}
              </>
            )}
          </div>

          <div className="flex items-center gap-2 border-t border-border/60 p-4">
            <input
              className="flex-1 rounded-lg border border-border bg-surface/70 px-3 py-2 text-sm text-slate-100 outline-none focus:border-primary/50"
              placeholder={active ? "Type a message…" : "Start a conversation to type"}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") sendText();
              }}
              disabled={!active}
            />
            <Button size="icon" onClick={sendText} disabled={!active || !draft.trim()}>
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Bubble({ role, text, live }: { role: "user" | "assistant"; text: string; live?: boolean }) {
  const isUser = role === "user";
  return (
    <div className={cn("flex gap-3", isUser ? "justify-end" : "justify-start")}>
      {!isUser ? (
        <span className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg border border-primary/40 bg-primary/10 text-primary">
          <Volume2 className="h-3.5 w-3.5" />
        </span>
      ) : null}
      <div
        className={cn(
          "max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
          isUser
            ? "bg-primary/15 text-slate-100"
            : "border border-border/70 bg-surface-2/70 text-slate-100",
          live && "opacity-80",
        )}
      >
        {text}
        {live ? <span className="ml-1 inline-block h-3 w-1.5 animate-pulse bg-primary align-middle" /> : null}
      </div>
    </div>
  );
}
