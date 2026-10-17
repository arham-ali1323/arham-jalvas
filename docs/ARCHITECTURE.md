# MARK LIV — Architecture

> Status: **as-built** description of the existing desktop application, plus the
> intended target architecture it will grow into. Written after a full read of
> the repository at the start of the platform migration.
>
> This document describes what exists today. Items marked **[TARGET]** do not
> exist yet and are tracked in `IMPLEMENTATION_PLAN.md`.

---

## 1. Executive summary

MARK LIV is today a **single Python desktop application** (one repository, no
packages) that provides a real-time, voice-driven AI assistant:

- **UI**: PyQt6 (`ui.py`, ~5,600 lines) — a JARVIS-style HUD with a software-rendered
  holographic avatar, activity log, metrics, and overlay settings panels.
- **Orchestration / AI session**: `main.py` (~2,440 lines) — the `JarvisLive` class
  opens a **Gemini Live (v1alpha/v1beta) real-time session**, streams microphone
  audio in, plays synthesized speech out, and dispatches tool calls.
- **AI**: Google GenAI Python SDK (`google-genai`). The conversational model is
  Gemini Live (`models/gemini-3.1-flash-live-preview` first rung). One-shot
  generation (vision, parsing, shell text) goes through `core/gemini.py`. A local
  LLM path (Ollama / OpenAI-compatible) exists in `core/llm_client.py`.
- **Capabilities**: 15 auto-discovered action modules (`actions/*.py`) + a
  drop-in plugin system (`plugins/*.py`) giving browser automation, file control,
  app launching, system settings, media, dev agents, and more.
- **Memory**: JSON-file based (`memory/long_term.json`) with categories, budgets,
  lexical recall, and session summaries.
- **Remote control**: an embedded **FastAPI + WebSocket dashboard**
  (`dashboard/server.py`) that lets a phone browser send commands and relay
  microphone audio. This is the single most important existing asset for the
  target web+desktop platform.

There is **no web application, no shared backend, no database, no user accounts,
and no device pairing in the modern sense** yet. The embedded dashboard is a
1-to-1 LAN remote, not a multi-user platform.

---

## 2. Runtime topology (today)

```
                      +-----------------------------------------------+
                      |                 main.py                       |
                      |                                               |
  python main.py ---> |  main() -> JarvisUI (ui.py, Qt main thread)   |
                      |     |                                         |
                      |     +-- daemon thread -> JarvisLive.run()     |
                      |            (asyncio event loop)               |
                      +-----------------------------------------------+
                                          |
        +---------------------------------+----------------------------------+
        |                    |                       |                       |
   GenAI Live SDK      sounddevice            core/gemini.py         dashboard/server.py
   (WebSocket)         InputStream/           (one-shot REST/Live)   (FastAPI :8000/:8001)
        |              RawOutputStream              |                       |
   Gemini cloud        mic / speakers         Gemini cloud          phone browser (LAN)
```

- **Threads**: Qt GUI on the main thread; the whole assistant runs in one daemon
  thread driving an `asyncio` event loop (`main.py:2432-2441`).
- **Cross-thread calls** are done through Qt signals exposed by `JarvisUI`
  (`write_log`, `set_state`, `push_visemes`, ...). `ui.py` never imports `main.py`;
  `main.py` injects callbacks into the UI object.

---

## 3. The conversation session (`main.py`, `JarvisLive`)

### 3.1 Constants (`main.py:107-111`)

| Constant | Value | Meaning |
|---|---|---|
| `LIVE_MODEL` | `models/gemini-3.1-flash-live-preview` | Current rung; reassigned from `core.gemini.live_model()` each connect |
| `CHANNELS` | `1` | Mono |
| `SEND_SAMPLE_RATE` | `16000` | Rate Gemini wants on input |
| `RECEIVE_SAMPLE_RATE` | `24000` | Rate Gemini emits on output |
| `CHUNK_SIZE` | `1024` | Frames per capture block (16 kHz grid) |

### 3.2 Lifecycle / reconnect loop (`main.py:2216-2427`)

1. `LIVE_MODEL = _gemini.live_model()` — pick a rung that is not in cooldown.
2. Build `LiveConnectConfig` via `_build_config()` (`main.py:1036-1147`).
3. Fresh `genai.Client(...)` per reconnect (avoids stale HTTP state).
4. `async with client.aio.live.connect(...) as session, asyncio.TaskGroup() as tg:`
   starts the concurrent tasks:

   | Task | Method | Responsibility |
   |---|---|---|
   | watch reconnect | `_watch_reconnect` | reacts to voluntary reconnect requests |
   | send realtime | `_send_realtime` (`main.py:1370`) | `out_queue` -> `send_realtime_input(audio=Blob("audio/pcm"))` |
   | listen audio | `_listen_audio` (`main.py:1385`) | mic capture -> wake/echo gates -> `out_queue` |
   | receive audio | `_receive_audio` (`main.py:1594`) | `session.receive()` loop; audio -> `audio_in_queue`; transcripts; tool calls |
   | play audio | `_play_audio` (`main.py:1723`) | `audio_in_queue` -> `RawOutputStream` + visemes |
   | system monitor | `_run_system_monitor` | background metric alerts |
   | background monitor | `_run_background_monitor` | daily topic news watch |
   | proactive mode | `_run_proactive_mode` | unprompted speech engine |
   | sleep watch | `_run_sleep_watch` | auto-sleep in wake-word mode |
   | phone audio relay | `_relay_phone_audio` | dashboard phone mic -> `out_queue` |
   | startup briefing | `_send_startup_briefing` | morning brief once per process |

5. Exceptions are classified in the `except BaseException` block
   (`main.py:2302-2412`): voluntary reconnect, rejected resumption handle,
   quota/unavailable (`_gemini.note_live_failure`), rejected tuning fields,
   rejected proactive audio, invalid API key, network errors. Network errors
   back off exponentially, capped at 60 s.

### 3.3 Session config (`_build_config`, `main.py:1036-1147`)

- `response_modalities=["AUDIO"]`
- `output_audio_transcription={}` and `input_audio_transcription={}`
- `system_instruction` = time context + identity + formatted memory + rendered
  `core/prompt.txt`
- `tools=[{"function_declarations": inline + actions + plugins}]`
- `session_resumption=SessionResumptionConfig(handle=self._resume_handle)`
- `context_window_compression=SlidingWindow()`
- prebuilt voice from `get_voice()` (whitelist in `config_manager.py`)
- optional: proactivity, `realtime_input_config` (AAD), `media_resolution`,
  `thinking_config`

### 3.4 Tool calling

- Inline declarations (`main.py:407-574`): `system_status`, `screen_process`,
  `close_camera`, `manage_monitor`, `shutdown_jarvis`, `save_memory`,
  `recall_memory`, `undo`, `open_app`, `browser_control`, `computer_control`,
  `computer_settings`, `desktop_control`, `file_controller`, `file_processor`,
  `code_helper`, `dev_agent`, `reminder`, `send_message`, `game_updater`,
  `video_player`, `web_search`, `weather_report`, `youtube_video`,
  `flight_finder`.
- File-backed actions discovered by `core.action_loader.discover_actions`
  (`main.py:695`).
- Plugins discovered by `core.plugin_loader.discover_plugins`
  (`main.py:703`).
- Dispatch in `_execute_tool` (`main.py:1202-1368`): inline first, then action
  registry, then plugin registry; result returned via `FunctionResponse`.
  `save_memory` short-circuits with `scheduling="SILENT"`.

### 3.5 Provider abstraction that already exists

| Layer | Abstraction | Notes |
|---|---|---|
| One-shot Gemini | `core/gemini.py` | Tiered model ladder (`FAST`/`SMART`/`SEARCH`/`LIVE`), cooldowns, REST fallback, unified `.text/.as_json` |
| Local LLM | `core/llm_client.py` | `get_llm_provider()` -> `"ollama"` or `"openai"` (LM Studio, LocalAI, ...), streamed events |
| TTS | `core/tts.py` | `create_tts_player(config)` — Edge / Kokoro / ElevenLabs |
| STT | `core/stt.py` | `WhisperSTT`, `VoskSTT` (no common base/factory) |
| Audio endpoints | `core/audio_devices.py` | host-API ladders, name-based selection, per-device working rate discovery |

There is **no unified "AI provider" interface bridging Gemini Live and local
LLMs for the conversation itself** — the conversation is always Gemini Live.

---

## 4. Audio pipeline

### 4.1 Microphone input (`_listen_audio`, `main.py:1385-1549`)

```
device (native rate, e.g. 48 kHz WASAPI)
    -> sd.InputStream(samplerate=cand.rate, blocksize=rate*1024/16000)
    -> callback:
         _StreamResampler(cand.rate -> 16000)   [Kaiser FIR + fractional interp]
         -> wake-word gate
         -> speaking / barge-in gate
         -> echo-tail guard (EchoGuard)
         -> push-to-talk gate
         -> out_queue.put_nowait({"data": pcm16, "mime_type": "audio/pcm"})
         -> HUD level
```

- `_StreamResampler` (`main.py:135-208`): 63-tap Kaiser-windowed anti-alias FIR
  streamed with a saved tail, plus fractional linear interpolation with carried
  sub-sample phase. Output int16 mono at 16 kHz. Skipped when the device already
  opens at 16 kHz.
- Device selection uses `core.audio_devices.input_candidates()`, which probes
  devices (WASAPI first), determines each one's **working capture rate**, and
  returns them best-first. Devices are stored by **name**, not index.
- The mic-open loop tolerates per-device failure and a total absence of usable
  microphones without tearing down the Gemini session (`main.py:1526-1537`).

### 4.2 Speaker output (`_play_audio`, `main.py:1723-1856`)

- `sd.RawOutputStream(samplerate=24000, channels=1, dtype="int16", blocksize=1024)`.
- Batches up to ~9600 bytes (~200 ms), computes 20 ms viseme frames
  (`_pcm_visemes`), writes via `asyncio.to_thread(stream.write, ...)`.
- Output latency read from `stream.latency` to size the echo tail.

### 4.3 The Windows microphone problem (motivation for Phase 2)

Observed error: `PortAudioError: Error opening InputStream [PaErrorCode -9999]`.

Cause: WASAPI shared mode runs at the hardware clock (48 kHz) and **refuses
16 kHz** (`Invalid sample rate [-9997]`); MME accepts 16 kHz but its hidden
conversion can fail with `Unanticipated host error [-9999]`. Forcing Gemini's
16 kHz onto capture is the bug. The fix (already in the working tree) captures
at the device's native rate and resamples to 16 kHz in the callback.

---

## 5. Capabilities: actions & plugins

### 5.1 Actions (`actions/*.py`)

Auto-discovered by `core/action_loader.py`: any module exposing a module-level
`TOOL` dict is registered. Optional `behavior` (`BLOCKING`/`NON_BLOCKING`) and
`scheduling` (`WHEN_IDLE`/`SILENT`/`INTERRUPT`).

| Category | Modules |
|---|---|
| System / desktop | `computer_control`, `computer_settings`, `desktop`, `open_app` |
| Background services (no `TOOL`) | `system_monitor`, `background_monitor`, `proactive` |
| Browser / web | `browser_control`, `web_search`, `youtube_video`, `weather_report`, `flight_finder` |
| Files | `file_controller`, `file_processor` |
| Media | `video_player`, `screen_processor` (service, no `TOOL`) |
| Productivity / dev | `code_helper`, `dev_agent`, `reminder`, `send_message`, `game_updater` |

All modules carry cross-platform branches; none is hard-Windows-only.
`screen_processor` is not a tool — `main.py` calls its capture functions directly
for vision.

### 5.2 Plugins (`plugins/*.py`)

A plugin is a single drop-in `.py` file (leading `_` means skipped). Contract
(`plugins/_template.py`):

- `PLUGIN = {"name", "description", "parameters"}` (parameters is a Gemini
  `OBJECT` schema).
- `run(parameters, player=None, session_memory=None) -> str`.
- Optional `PLUGIN_SETTINGS` (self-describing settings UI), `behavior`,
  `scheduling`.

`core/plugin_loader.py` discovers/validates/dedupes and reads enabled-state from
config on every call (no restart needed to toggle).

---

## 6. Memory & configuration

### 6.1 Long-term memory (`memory/memory_manager.py`)

- Storage: `memory/long_term.json` (plaintext, git-ignored).
- Shape: `{category: {key: {"value": str, "updated": "YYYY-MM-DD"}}}` for
  categories `identity, preferences, projects, relationships, wishes, notes`,
  plus a `sessions` list (max 3 summaries).
- Limits: 380 chars/value, 200,000 chars total (oldest trimmed), prompt budget
  900 core chars + 420 index chars + 6 per category.
- API: `load_memory`, `update_memory`, `format_memory_for_prompt`,
  `search_memory`, `remember`, `forget`, `save_session_summary`,
  `pop_last_session`, `set_trim_notifier`.

### 6.2 Configuration (`memory/config_manager.py`)

Single JSON file `config/api_keys.json` (read-modify-write per call, plaintext,
git-ignored). Keys include: `gemini_api_key`, `assistant_name`, `user_name`,
`voice_name`, `wake_word_enabled`, `push_to_talk_enabled`, `hud_style`,
`thinking_enabled`, `turn_tuning`, `proactive_audio`, `media_resolution`,
`morning_brief_enabled`, `input_device`/`output_device` (by name),
`plugins_enabled`, `plugin_config`.

`config/__init__.py` is a separate read-only reader of the same file plus OS
detection. Many `actions/*.py` and `dashboard/server.py` read the raw JSON
directly.

### 6.3 System prompt

`core/prompt.txt`, rendered with `str.replace` (not `str.format`) so stray braces
cannot crash startup. Tokens: `{assistant_name}`, `{platform}`, `{capabilities}`,
`{limits}`.

---

## 7. Existing remote dashboard (`dashboard/server.py`)

The most reusable asset for the target platform. Key facts:

- FastAPI app, port **8000** (HTTPS alias on **8001**), bound to `0.0.0.0`.
- Self-signed TLS auto-generated `config/certs/jarvis.{key,crt}`; firewall /
  network-profile auto-configuration on startup.
- Auth: one-time 6-char key -> 32-byte bearer token in an **in-memory set**;
  device tokens in `localStorage` exchanged via `/api/device-login` with **no
  expiry**.
- Routes: `/login`, `/auto-login`, `/api/device-login`, `/api/revoke-devices`,
  `/api/command`, `/api/wake`, `/api/upload`, `/api/files`, `/ws` (commands),
  `/ws/phone-audio` (PCM relay).
- AES-256-CBC app-layer encryption with a **hardcoded salt**
  (`JARVIS-DASHBOARD-v1`) and a key derived from the 6-char PIN; plaintext
  fallback accepted.
- **No CORS middleware**, no Origin validation.
- Transport-only: it never touches the desktop; commands flow through
  `_command_queue` consumed by `main._process_dashboard_commands`
  (`main.py:2147-2176`), which injects text into the live session.

This is a working WebSocket + command-ingress pattern that the new shared backend
can build on, but it is **not** multi-user, has no database, and its auth model is
not suitable for the public internet as-is.

---

## 8. Known bugs, risks, and fragile areas

Confirmed during analysis (quote-verified, not all fixed):

1. `main.py:617` — `self._asst_name = "JARVI    S"` (typo with spaces). Cosmetic
   but used as the assistant name on some code paths.
2. `main.py:2396` — reconnect path assigns the bare local `_conn_backoff = 3`
   instead of `self._conn_backoff`, relying on a later read; works by accident.
3. Voice **barge-in is disabled** (`main.py:1435-1444`); interrupting the
   assistant by voice is incomplete.
4. `core/llm_client.py::call_llm_text` always uses the Ollama endpoint and body
   even when provider is `"openai"`; hardcoded 150-token output caps.
5. `core/gemini.py` — Live thread/semaphore release race; `note_live_failure`
   does not cool on 503/504.
6. `core/tts.py` — Kokoro path can `pip install` at runtime; `TTSPlayer.stop()`
   calls global `sd.stop()`.
7. `core/audio_devices.py` — `configure()` clears `_cache` but not the probe /
   input-rate caches.
8. Memory/config writes are **non-atomic** (no temp-file + rename); a crash
   mid-write corrupts the file and readers silently return `{}`.
9. Dashboard auth state (`_tokens`, `_device_sessions`, `_aes_cache`) grows
   unbounded; `/api/wake` is a no-op; `/api/revoke-devices` has no UI.
10. Security: secrets in query strings, permanent device tokens, hardcoded AES
    salt, plaintext fallback, no CORS/Origin checks, broad firewall changes.
11. `readme.md` claims memory "nothing is deleted", but `_trim_to_limit` deletes
    oldest entries at 200k chars.

These are catalogued for triage in `IMPLEMENTATION_PLAN.md`.

---

## 9. Target architecture [TARGET]

A monorepo with three deployable components plus shared assets.

```
Mark-LV/
├── apps/
│   ├── web/        Next.js App Router + TS + Tailwind + shadcn/ui + Framer Motion  (Vercel)
│   └── desktop/    existing Python + PyQt6 app (moved here incrementally)
├── services/
│   └── api/        FastAPI + WebSockets + PostgreSQL + SQLAlchemy + Alembic
├── packages/
│   └── shared/     shared TS types / schemas (web <-> api)
├── docs/
├── .env.example
├── README.md
└── docker-compose.yml
```

### 9.1 Component responsibilities

**A. MARK LIV Web (Next.js, Vercel)**
Dashboard, streaming chat, live voice conversations, conversation history, auth,
settings, voice selection, dark/light mode, animated visualizer, connection
status. Talks to `services/api` over HTTPS + WebSocket. Never exposes a permanent
Gemini key to the browser — real-time voice is brokered through the backend with
short-lived credentials/session tokens.

**B. MARK LIV Desktop (existing Python/PyQt6)**
All current features preserved. Adds: system tray, background operation,
optional wake word (exists), first-run setup, device pairing, packaged Windows
executable via PyInstaller.

**C. MARK LIV Backend (`services/api`)**
Auth integration, conversations + messages, user preferences, paired devices,
device permissions, action history, AI provider configuration, secure
communication, streaming text responses, persistent storage. Deployable
independently of Vercel on a platform with persistent processes + WebSockets.

### 9.2 AI provider abstraction [TARGET]

A single `AIProvider` interface (chat stream, live session, tool schema, auth
requirements) with implementations:
`GeminiProvider` (text + Live), `LocalLLMProvider` (Ollama/OpenAI-compatible).
The existing `core/gemini.py`, `core/llm_client.py`, and the Live session in
`main.py` are wrapped, not rewritten.

### 9.3 Real-time transport for browsers [TARGET]

The browser must not hold a permanent Gemini key. The backend:
1. authenticates the user,
2. opens/relays the Gemini Live session (or issues an ephemeral token where the
   Gemini API supports it),
3. relays PCM over a WebSocket with back-pressure.
The web client does mic capture (`getUserMedia` + AudioWorklet) and PCM
playback, plus an animated visualizer.

### 9.4 Web <-> Desktop pairing [BUILT]

- Desktop starts a pairing, shows a short code, and polls until the signed-in
  web user approves it. Approval issues a one-time device token, stored only as
  a sha256 hash server-side and in the local `companion` config block.
- Backend stores paired devices (`PairedDevice`), scoped permissions
  (`DevicePermission`) and `ActionHistory`. The companion holds a WebSocket at
  `/devices/companion?token=...`; command results are written back to the
  history row.
- Web sends a **validated allowlisted command** (`POST /devices/{id}/command`);
  the server validates against `device_actions.py` and checks the device's
  granted scope, then the desktop companion re-validates against its own copy
  (`core/desktop_actions.py`) before executing.
- Sensitive actions (`screen.lock`, `power.*`) carry `requires_confirmation`:
  the desktop refuses to run them without an on-device confirmation callback.
- No arbitrary shell, no unrestricted AI-generated commands. Revoking a device
  destroys its token hash and closes its socket immediately.
- Both allowlist copies are kept in step by tests that assert the names,
  permissions and confirmation flags agree (server and desktop suites).

### 9.5 Data model [TARGET]

`users`, `conversations`, `messages`, `user_preferences`, `paired_devices`,
`device_permissions`, `action_history`. Managed PostgreSQL + Alembic migrations.
Per-account data isolation; passwords hashed (never plaintext).

---

## 10. Migration strategy

- **Add, don't move first.** Create `apps/`, `services/`, `packages/`, `docs/`
  alongside the existing tree and scaffold new code there. Only relocate the
  desktop app into `apps/desktop/` once imports, `BASE_DIR`, PyInstaller spec,
  and asset paths are audited (see plan Phase 7).
- Preserve every existing feature; the desktop app must keep launching
  throughout.
- Reuse `dashboard/server.py` patterns (auth, command queue, broadcast, TLS)
  rather than inventing new transport from scratch.
- Extract `packages/shared` types before wiring web<->api to avoid drift.
