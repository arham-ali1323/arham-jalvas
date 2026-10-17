# MARK LIV — Implementation Plan

> Companion to `ARCHITECTURE.md`. This is the working plan for turning the
> existing Python desktop assistant into a professional web + desktop AI
> platform. It is organized by the eight requested phases, followed by a
> prioritized backlog and an explicit list of non-goals.

---

## Guiding rules (from the brief)

1. Do not delete existing working functionality.
2. Do not rewrite the project unnecessarily.
3. Inspect before modifying.
4. Prefer reusable, maintainable components.
5. TypeScript for the web frontend.
6. Proper Python typing where practical.
7. No hardcoded secrets.
8. No mock data presented as production data.
9. Clearly identify incomplete features.
10. Loading and error states everywhere.
11. Responsive UI.
12. Run relevant tests after each phase.
13. Fix build and type errors.
14. Document architectural decisions.
15. Explain major changes before destructive ones.
16. Never claim a feature works without verification.

---

## Phase status

| Phase | Name | Status |
|---|---|---|
| 1 | Codebase analysis + docs | **Done** (this document + `ARCHITECTURE.md`) |
| 2 | Desktop stability (mic/audio) | **Done** (resampler + candidate selection; desktop tests pass) |
| 3 | Shared backend (FastAPI) | **Done** (auth, conversations, chat SSE, live relay, devices) |
| 4 | Web application (Next.js) | **Done** (auth, chat, live voice, devices, settings) |
| 5 | Live voice (web) | **Done** (relay + tickets + worklet capture + playback + visualizer; tests pass — see `LIVE_VOICE.md`) |
| 6 | Desktop pairing | **Implemented** (pairing + allowlist + companion + Devices page; 51 API / 64 desktop tests pass; GUI setup still incomplete) |
| 7 | Windows packaging | **Built + launched on Windows** — `mark_liv.spec`, onedir package (~310 MB); updater deferred |
| 8 | Deployment | **Prepared, not deployed** — Compose/Vercel docs and local checks; hosted Docker/PostgreSQL/TLS not verified |

---

## Phase 1 — Codebase analysis (COMPLETE)

Deliverables:
- `docs/ARCHITECTURE.md` — as-built architecture, target architecture, known bugs.
- `docs/IMPLEMENTATION_PLAN.md` — this file.
- Prioritized task list (below).

Outcome: the existing app is a well-factored single-module Python monolith with a
surprisingly complete tool/plugin/memory stack and an embedded FastAPI dashboard
that is the natural seed for the shared backend.

---

## Phase 2 — Desktop stability (IN PROGRESS)

### 2.1 Objective

Eliminate `PortAudioError: Error opening InputStream [PaErrorCode -9999]` on
Windows, make microphone selection robust across machines, and preserve speaker
output. Do not break anything else.

### 2.2 Work already present in the working tree (uncommitted)

`core/audio_devices.py`:
- Separate host-API preference order for input (`wasapi, mme, directsound`).
- `_working_input_rate(idx)` probes each input device for a rate that actually
  opens (native first: 48k/44.1k/32k/16k/8k), cached per device.
- `input_candidates(name)` returns ordered `InputCandidate(device, rate, name,
  backend)` records, WASAPI-first, only devices that opened.
- `_usable("input")` now accepts any working rate instead of demanding 16 kHz.

`main.py`:
- `_StreamResampler` (Kaiser FIR + fractional interpolation) converts native
  capture rate -> 16 kHz in the audio callback.
- `_listen_audio` walks `input_candidates()`, opens the first that works, swaps
  the resampler to match, and reopens on stream failure without killing the
  session. No usable mic -> retry every 5 s instead of raising.

### 2.3 Remaining Phase 2 tasks

- [ ] **Audit the resampler math** — verify passband/aliasing and block-timing
      behaviour with a synthetic test (sine sweep, impulse, DC), not just by
      reading it.
- [ ] **Verify `input_candidates` correctness** — dedupe, pseudo-device
      filtering, name-prefix matching, "system default" fallback.
- [ ] **Confirm `configure()` cache invalidation** — `_input_rate_cache` and
      `_probe_results` should reset when rates change (`audio_devices.py`).
- [ ] **Diagnostic logging** — one clear log line per mic decision (device,
      backend, capture rate -> 16 kHz); already partly done.
- [ ] **Speaker regression check** — ensure `resolve(name,"output")` at 24 kHz
      and `_play_audio` are untouched.
- [ ] **Graceful mic permission / disconnected-device errors** surfaced to the UI
      log (partly done).
- [ ] **Smoke test** — `python -c "import main"` and a headless
      `main.JarvisLive` construction where possible; `python main.py` launch on
      Windows if hardware is available.
- [ ] Fix the two confirmed bugs while in here: `_asst_name` typo (`main.py:617`)
      and the `_conn_backoff` local-vs-attribute slip (`main.py:2396`).

### 2.4 Verification for this phase

There is no test suite in the repo. Add a minimal `tests/` with:
- `test_resampler.py` — frequency/DC/impulse + block-boundary continuity.
- `test_audio_candidates.py` — selection/dedupe logic with a stubbed
  `sounddevice`.
- `test_imports.py` — imports `core.audio_devices`, `core.gemini`, `memory.*`
  without a mic.

Run: `python -m pytest -q` (add `pytest` as a dev dependency).

---

## Phase 3 — Shared backend (`services/api`)

Scaffold a FastAPI service independent of the desktop and Vercel.

- [x] FastAPI app skeleton with `/health` and `/health/ready`.
- [x] Settings via `pydantic-settings` + `.env` (no secrets in code).
- [x] SQLAlchemy 2.x async engine + sessions; PostgreSQL in prod, SQLite in dev.
- [x] Alembic migrations; initial schema for `users`, `conversations`,
      `messages`, `user_preferences`, `paired_devices`, `device_permissions`,
      `action_history`. (Revision `724aed8afa0f`; upgrade/downgrade verified
      against SQLite.)
- [x] Auth: self-hosted **JWT** access/refresh (`pyjwt`) with **Argon2id**
      password hashing (`argon2-cffi`). Register, login, refresh, me, logout,
      token-based password reset (hashed tokens). Protected `get_current_user`
      dependency.
- [x] Conversations/messages CRUD scoped to the authenticated user (404, not
      403, so other users' IDs are indistinguishable from absent).
- [x] Streaming text chat endpoint (SSE) backed by the AI provider abstraction
      (`AIProvider` / `GeminiProvider`; returns 503 rather than fabricating).
- [ ] WebSocket echo/channel skeleton for future voice + pairing.
- [~] Rate limiting + structured logging; request validation done via pydantic.
- [x] Tests: auth, ownership isolation, chat streaming/persistence (13 pass);
      migration upgrade/downgrade verified manually. `Dockerfile` +
      `docker-compose.yml` provided (not executed — Docker absent on this host).

Reference: reuse patterns proven in `dashboard/server.py` (command queue,
broadcast, graceful dependency gating) but with real persistence and a proper
auth model.

---

## Phase 4 — Web application (`apps/web`)

Next.js App Router + TypeScript + Tailwind + shadcn/ui + Framer Motion + Lucide.

- [x] Project scaffold with strict TS, ESLint/Prettier, dark theme tokens.
      (`next build`, `tsc --noEmit`, and `next lint` all pass.)
- [x] Auth screens (register, login, forgot/reset password) wired to the API via
      a BFF with **httpOnly cookies** — tokens never touch client JS.
- [~] Protected app shell: sidebar has Chat (with integrated history), Voice,
      Devices, Settings, Account, and a New chat action. Dashboard not built.
- [x] Streaming chat view with loading/error/empty states (SSE through the proxy).
- [x] Conversation history (list + detail), persisted server-side.
- [~] Settings: AI model + provider status done. Voice/mic/speaker/theme/prefs and
      connected-desktop status are explicitly deferred (no placeholder data).
- [x] Premium JARVIS-style visual language: dark background, cyan/electric-blue
      accents, neon glow, glassmorphism, Framer Motion animation, responsive.
- [~] Typed API client in `src/lib`. Connection status indicators not yet built;
      types are hand-written, not generated from `packages/shared`.
- [~] `next build` + `tsc --noEmit` pass; component/e2e tests not yet written.

---

## Phase 5 — Live voice (web) — DONE

Design and full detail: `docs/LIVE_VOICE.md`.

- [x] Mic capture (`getUserMedia` + AudioWorklet) -> PCM16 16 kHz, with streaming
      linear resampling from the device's native rate.
- [x] PCM playback at 24 kHz with a running-clock jitter buffer + interruption
      (barge-in stops scheduled sources).
- [x] Backend-brokered Gemini Live session over WebSocket. The permanent key
      stays server-side; the browser gets a short-lived **single-use** ticket.
- [x] Animated voice visualizer reflecting input/output levels and AI state
      (listening / thinking / speaking).
- [x] Permission-error, device-disconnect, and API-disconnect handling.
- [x] Bounded reconnection with exponential backoff (max 5 attempts).
- [x] Per-user rate limiting + concurrent-session cap.
- [x] Tests: `services/api/tests/test_live.py` (tickets, limiter, translation,
      bridge, HTTP endpoint, and a real WS round-trip) — 15 tests.

Not yet done (tracked, not faked): tool calling and transcript persistence over
the live relay; session resumption; multi-worker ticket store (needs Redis).

---

## Phase 6 — Desktop pairing  (COMPLETE)

- [x] Backend: paired-device model (`PairedDevice`, `DevicePermission`,
      `ActionHistory`), pairing codes, scoped permissions, action history, revoke
      endpoint. See `services/api/app/routes/devices.py`.
- [x] Desktop: companion registration + pairing UI (`core/device_companion.py`),
      persistent device credential stored in `memory/config_manager.py` (the
      `companion` block, replacing the old permanent in-RAM remote token).
- [x] Allowlisted command set with strict validation (`device_actions.py` on the
      server, `core/desktop_actions.py` on the desktop — two copies kept in step
      by tests); sensitive actions require on-device confirmation; no arbitrary
      shell; no unrestricted AI-generated commands.
- [x] Credential handling: the device token is issued once, stored only as a
      sha256 hash server-side, and looked up by hash (so there is no secret to
      compare in constant time). Revoke clears the hash and closes the socket.
- [x] Web: "Connected devices" page (`apps/web/src/app/(app)/devices/page.tsx`)
      showing online status, per-scope permission editing, a command form built
      from the live allowlist catalog, recent activity, and a revoke control.
- [x] Transport: the companion socket carries its credential in the URL query
      (the browser/`websockets` client cannot set an Authorization header on the
      upgrade); deploy behind TLS so the URL is never in the clear.

Verification: `services/api` 44 tests (16 device tests incl. a real WS
round-trip), desktop 57 tests, `npm run build` clean.

---

## Phase 7 — Windows packaging  (COMPLETE except the updater; see `docs/PACKAGING.md`)

- [x] Audit `get_base_dir()` / `BASE_DIR` usage for frozen builds — every call
      site now delegates to `core/paths.py`, which splits **bundled read-only
      resources** (`resource_path` → `sys._MEIPASS`) from **writable state**
      (`data_dir` → beside the exe). `tests/test_paths.py` pins the difference,
      and `packaging/build_smoke.py` proves it in a real PyInstaller binary.
- [x] PyInstaller spec bundling assets (`core/face_model.obj`, `core/prompt.txt`,
      `config/jarvis.ico`, `actions/`, `plugins/`, `dashboard/static`). Playwright
      browser policy and the wake-word model note are in `docs/PACKAGING.md`.
- [x] First-run setup / AI configuration / mic-speaker selection already exist in
      the app; the frozen build boots into them (verified).
- [ ] Safe, verifiable update mechanism (signed manifest / checksum) — deferred.
- [x] Build and **actually test** the executable on Windows: `mark_liv.spec`
      builds a ~660 MB onedir app that boots and stays up; bundled resources
      land under `_internal/` and state resolves beside the exe.

---

## Phase 8 — Deployment preparation  (NOT DEPLOYED; see `docs/DEPLOYMENT.md`)

- [x] Web -> Next.js **standalone** container (or Vercel); public env vars are
      build args, documented in `apps/web/.env.example`.
- [x] API Docker image and persistent-host/WebSocket guidance (not deployed);
      single-worker caveat documented (in-process pairing/hub/ticket state).
- [x] PostgreSQL 16 Compose configuration and migrations. Local SQLite
      `alembic upgrade head` and `alembic check` passed; PostgreSQL not tested.
- [x] `docker-compose.yml`: db + api + web, healthchecks gated on real readiness
      (`/health/ready`), `restart: unless-stopped`, required `JWT_SECRET`.
- [x] `.env.example` files for each component; secrets git-ignored.
- [x] Health checks, CORS allowlist, WebSocket (Upgrade) proxy guidance, build
      scripts (`docker compose up --build`).
- [x] Verified locally: Next.js production build/routes; FastAPI `/health` and
      `/health/ready` on temporary SQLite; migration/model parity; production
      configuration guards.
- [ ] Docker image/Compose healthcheck and real TLS-host end-to-end (Docker was
      unavailable in the verification environment).
- [ ] End-to-end on real TLS hosts (needs infrastructure; instructions ready).

---

## Prioritized backlog

Ordered by impact/effort. P0 = do first.

### P0 — Correctness & safety
1. Finish and verify the Phase 2 microphone/resampler fix (tests + smoke run).
2. Fix `_asst_name` typo and `_conn_backoff` slip (`main.py`).
3. Make `memory/config_manager.py` + `memory/memory_manager.py` writes atomic
   (temp file + `os.replace`) to prevent corruption.
4. Fix `audio_devices.configure()` to clear probe/input-rate caches.

### P1 — Reusable foundations
5. Define the `AIProvider` abstraction and wrap existing `core/gemini.py` /
   `core/llm_client.py` behind it.
6. Extract typed request/response schemas; seed `packages/shared`.
7. Scaffold `services/api` with health checks, settings, DB, migrations.

### P2 — Platform features
8. Auth + conversations + streaming chat (backend), then auth + chat (web).
9. Settings + conversation history in the web app.
10. Web live voice over backend-brokered Live sessions.
11. Desktop pairing + allowlisted remote actions.

### P3 — Distribution & polish
12. PyInstaller packaging + updater.
13. Deployment (Vercel + persistent API + managed Postgres).
14. Rate limiting, structured logging, error boundaries, WebSocket cleanup.

---

## Explicit non-goals / guardrails

- **No arbitrary remote shell** from the web, ever.
- **No unrestricted AI-generated command execution** on the desktop.
- **No permanent Gemini API key in a browser.**
- **No local file access** from the web without explicit user authorization.
- **No deleting** working desktop functionality to simplify a refactor.
- **No mock data** presented as real production behavior.
- **No credentials in Git.**

---

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Moving files breaks imports / PyInstaller paths | Keep desktop in place until Phase 7; audit `BASE_DIR`, `sys.modules` reuse, asset paths first |
| Web leaks Gemini key | Broker Live via backend; ephemeral tokens where supported |
| Pairing becomes an RCE vector | Allowlist + validation + explicit consent + audit log |
| Audio regressions | Add resampler + candidate tests before further edits |
| Scope creep | Strict phase gating; each phase ends with a written report |

---

## Phase report template (used at the end of every phase)

- What was completed.
- Which files changed.
- What was tested (and how).
- What remains incomplete.
- What should be implemented next.
