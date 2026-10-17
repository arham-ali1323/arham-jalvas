/**
 * MARK LIV microphone capture worklet.
 *
 * Runs on the audio render thread (not the main thread) so capture never stutters
 * when React re-renders. It converts the microphone's native stream into exactly
 * what Gemini Live wants: mono PCM16 at 16 kHz.
 *
 * The browser hands us Float32 blocks at the AudioContext's own rate — usually
 * 48 kHz, sometimes 44.1 kHz — so a real resampler is required. Decimating 48k
 * to 16k by throwing samples away would alias everything above 8 kHz back into
 * the speech band. Instead we do streaming linear interpolation with a carried
 * fractional phase, which is inaudible for speech and cheap enough for the audio
 * thread. (The desktop app uses a windowed-sinc FIR because it has the CPU to
 * spare; here, linear interpolation is the right trade-off.)
 *
 * Messages out:
 *   { type: "pcm", data: ArrayBuffer }   Int16 little-endian mono @ targetRate
 *   { type: "level", value: 0..1 }       input loudness for the visualizer
 * Messages in:
 *   { type: "mute", value: boolean }
 */

const TARGET_RATE = 16000;
const LEVEL_POST_INTERVAL = 4; // post the level every N render quanta (~12ms)

class CaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const opts = (options && options.processorOptions) || {};
    const target = opts.targetRate || TARGET_RATE;
    this.ratio = sampleRate / target; // input samples per output sample
    this.buffer = new Float32Array(0); // unconsumed input
    this.pos = 0; // fractional read position within `buffer`
    this.muted = false;
    this.blocks = 0;

    this.port.onmessage = (event) => {
      const msg = event.data;
      if (msg && msg.type === "mute") this.muted = !!msg.value;
    };
  }

  _append(chunk) {
    const merged = new Float32Array(this.buffer.length + chunk.length);
    merged.set(this.buffer, 0);
    merged.set(chunk, this.buffer.length);
    this.buffer = merged;
  }

  process(inputs) {
    const input = inputs[0];
    const channel = input && input[0];
    if (!channel || channel.length === 0) return true;

    if (this.muted) {
      this.port.postMessage({ type: "level", value: 0 });
      return true;
    }

    // Loudness of this block, for the visualizer. RMS -> a 0..1 display value.
    let sum = 0;
    for (let i = 0; i < channel.length; i++) sum += channel[i] * channel[i];
    const rms = Math.sqrt(sum / channel.length);

    this._append(channel);

    // How many whole output samples we can produce without reading past the end?
    const span = this.buffer.length - 1;
    let count = 0;
    if (span > this.pos) {
      count = Math.floor((span - this.pos) / this.ratio) + 1;
    }
    if (count > 0) {
      const out = new Int16Array(count);
      for (let k = 0; k < count; k++) {
        const idx = this.pos + k * this.ratio;
        const i0 = Math.floor(idx);
        const frac = idx - i0;
        const s = this.buffer[i0] * (1 - frac) + this.buffer[i0 + 1] * frac;
        const clamped = s < -1 ? -1 : s > 1 ? 1 : s;
        out[k] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
      }
      // Carry the unconsumed tail and the fractional phase into the next call.
      const consumed = Math.floor(this.pos + count * this.ratio);
      const keepFrom = consumed;
      this.buffer = this.buffer.slice(keepFrom);
      this.pos = this.pos + count * this.ratio - keepFrom;
      this.port.postMessage({ type: "pcm", data: out.buffer }, [out.buffer]);
    }

    if (this.blocks % LEVEL_POST_INTERVAL === 0) {
      this.port.postMessage({ type: "level", value: Math.min(1, rms * 3.5) });
    }
    this.blocks++;
    return true;
  }
}

registerProcessor("mark-liv-capture", CaptureProcessor);
