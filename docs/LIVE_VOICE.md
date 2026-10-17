# MARK LIV — Live Voice (Phase 5)

> How the browser gets a real-time spoken conversation with Gemini Live without
> ever holding the Gemini API key, and what guarantees the transport makes.

---

## 1. The constraint that shapes everything

The brief has one non-negotiable rule:

> **Do not expose permanent Gemini API keys to browsers.**

A browser cannot be trusted with a long-lived key (it lives in devtools, network
tabs and memory), and a browser **WebSocket cannot set an `Authorization`
header**, so the two obvious designs — key in the client, or access token in the
query string — are both wrong.

The chosen design is a **server-brokered relay**:

```
Browser  ── HTTPS ──►  POST /live/ticket      (bearer cookie → short-lived ticket)
Browser  ── WSS  ───►  WS  /live/session?ticket=…
                          │
                          ├── server opens a Gemini Live session (secret key, server-side)
                          ├── browser → server:  PCM16 mono @ 16 kHz (binary frames)
                          └── server  → browser: PCM16 mono @ 24 kHz (binary) + JSON control
```

The browser only ever sees PCM and small control frames.

---

## 2. The ticket exchange

`POST /live/ticket` (authenticated) returns a random, **single-use** token that
expires after `LIVE_TICKET_TTL_SECONDS` (default 60 s). The WebSocket consumes
the ticket on first connect; a replay is refused with close code `4401`.

Why this is safe even though the ticket appears in the URL:
- it is worthless after ~60 s,
- it can be used **once**,
- it authorises nothing but a single voice session for a single account.

**Known limitation (stated, not hidden):** the ticket store is in-process. On a
multi-worker deployment a ticket minted by one worker is not visible to another,
so the exchange is only guaranteed correct with a single worker or sticky
routing. Swapping the dict for Redis behind `TicketStore.issue/consume` fixes it
without touching callers. See `app/services/live_tickets.py`.

---

## 3. Wire protocol

Browser → server:

| Frame | Meaning |
|---|---|
| binary | microphone PCM16 little-endian mono @ 16 kHz |
| `{"type":"text","text":"…"}` | a typed turn |
| `{"type":"activity_start"}` / `{"type":"activity_end"}` | manual VAD / push-to-talk |
| `{"type":"close"}` | end the session |

Server → browser:

| Frame | Meaning |
|---|---|
| binary | model audio, PCM16 little-endian mono @ 24 kHz |
| `{"type":"ready","input_rate":16000,"output_rate":24000,"voice":"…"}` | session is live |
| `{"type":"input_transcript","text":"…"}` | what the user said |
| `{"type":"output_transcript","text":"…"}` | what the model is saying |
| `{"type":"turn_complete"}` | the model finished a turn |
| `{"type":"interrupted"}` | the model was barged in on |
| `{"type":"error","message":"…"}` | a reportable failure |

Binary for audio (no base64 overhead), JSON text for control. This is a deliberate
choice for both bandwidth and simplicity.

---

## 4. Audio pipeline

**Capture (browser).** `getUserMedia` → `AudioWorkletNode` (`public/worklets/capture.worklet.js`).
The microphone usually runs at 48 kHz; the worklet performs streaming **linear
resampling with carried fractional phase** down to 16 kHz and converts to PCM16.
It runs on the audio render thread so React re-renders never cause a drop.
(The desktop app uses a windowed-sinc FIR because it has CPU headroom; in a
browser tab, linear interpolation is the correct trade-off.)

**Playback (browser).** Each 24 kHz PCM frame becomes an `AudioBuffer` scheduled
on the AudioContext clock with an ~80 ms lead and a **running `scheduledTime`**,
which yields gapless playback without per-frame gaps. Barge-in: on `interrupted`
(or on stop) every scheduled `AudioBufferSourceNode` is stopped and the clock is
reset.

**Barge-in.** The microphone streams continuously, so Gemini's own VAD detects
the user speaking and emits `interrupted`; the client then cuts playback. No
custom local VAD is required.

---

## 5. Reliability

- **Bounded reconnection.** Unexpected closes retry with exponential backoff
  (0.5 s → 8 s), **max 5 attempts**, each with a fresh ticket. A successful
  `ready` resets the counter. `4401` (bad/expired ticket) and `4429` (too many
  sessions) are treated as terminal and surface a clear message instead of
  looping.
- **Quota guards.** `LIVE_CONNECT_ATTEMPTS_PER_MINUTE` limits ticket minting per
  user; `LIVE_MAX_CONCURRENT_SESSIONS` caps simultaneous live sessions per user.
  Both live in `app/services/ratelimit.py` and `live_tickets.py`.
- **Cleanup.** `stop()` tears down the worklet, tracks, AudioContext and socket;
  the server releases its concurrency slot in a `finally`.
- **Microphone errors.** Permission / missing-device / device-busy failures are
  mapped to human messages before they reach the UI.

---

## 6. Code map

| Concern | File |
|---|---|
| Ticket store, session registry | `services/api/app/services/live_tickets.py` |
| Rate limiter | `services/api/app/services/ratelimit.py` |
| Provider + bridge + translation | `services/api/app/services/live.py` |
| Routes (`/live/ticket`, WS `/live/session`) | `services/api/app/routes/live.py` |
| Schemas | `services/api/app/schemas/live.py` |
| Browser client | `apps/web/src/lib/live.ts` |
| Capture worklet | `apps/web/public/worklets/capture.worklet.js` |
| Visualizer | `apps/web/src/components/voice/visualizer.tsx` |
| Voice page | `apps/web/src/app/(app)/voice/page.tsx` |
| Backend tests | `services/api/tests/test_live.py` |

---

## 7. Not done yet (honest scope)

- **Tool calling over the live relay.** The desktop session dispatches tool
  calls; the browser relay currently forwards only audio + transcripts. Wiring
  function calling through the web session is a follow-up.
- **Session resumption / context window compression** on the relayed session.
- **Persisting voice transcripts** to `conversations`. The web session is
  currently ephemeral; text chat is the persisted path.
- **Voice activity indicators from the server** (the UI derives listening /
  thinking / speaking from transcript and audio events).
- The ticket/limiter stores are single-process (see §2).
