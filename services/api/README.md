# MARK LIV Backend (`services/api`)

FastAPI + WebSockets + PostgreSQL service that backs the web application and the
desktop companion: authentication, conversations, messages, user preferences,
paired devices, device permissions, action history, and streaming AI chat.

This service is designed to run as a **persistent process** (WebSockets and
long-lived connections) — not inside a Vercel serverless function.

## Layout

```
services/api/
├── app/
│   ├── main.py            # FastAPI app factory + router wiring + CORS
│   ├── config.py          # pydantic-settings (env / .env)
│   ├── deps.py            # get_db, get_current_user
│   ├── database/          # async engine, session factory, declarative Base
│   ├── models/            # users, conversations, messages, preferences,
│   │                      # paired_devices, device_permissions, action_history
│   ├── schemas/           # pydantic request/response models
│   ├── routes/            # health, auth, conversations, chat, live, devices
│   └── services/          # security (argon2 + JWT), ai provider, email
├── alembic/               # migrations
├── tests/                 # pytest suite (SQLite, no external services)
├── Dockerfile
├── requirements.txt
└── .env.example
```

## Local development

```bash
cd services/api
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -r requirements.txt
cp .env.example .env                               # then edit
python -m alembic upgrade head                     # create the schema
uvicorn app.main:app --reload --port 8080
```

SQLite (`sqlite+aiosqlite:///./mark_liv_dev.db`) is the default `DATABASE_URL`,
so no database server is required to develop or test.

### Tests

```bash
python -m pytest -q
```

The suite runs against a throwaway SQLite file and a fake AI provider; it needs
no network and no PostgreSQL.

## Authentication

- Passwords are hashed with **Argon2id** (never stored in plaintext).
- **JWT** access tokens (default 30 min) and refresh tokens (default 30 days),
  signed with `JWT_SECRET`.
- `Authorization: Bearer <access_token>` on protected routes.
- Password reset is token-based; the token is stored only as a SHA-256 hash.
  `EMAIL_BACKEND=console` (development) writes the reset link to the log;
  `EMAIL_BACKEND=smtp` sends real mail.

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | – | Liveness |
| GET | `/health/ready` | – | Readiness (checks the DB) |
| POST | `/auth/register` | – | Create account, returns tokens |
| POST | `/auth/login` | – | Email + password -> tokens |
| POST | `/auth/refresh` | – | Refresh token -> new tokens |
| GET | `/auth/me` | Bearer | Current user |
| POST | `/auth/logout` | Bearer | Stateless ack (client drops tokens) |
| POST | `/auth/password-reset/request` | – | Request reset (always 202) |
| POST | `/auth/password-reset/confirm` | – | Set a new password |
| GET | `/conversations` | Bearer | List the caller's conversations |
| POST | `/conversations` | Bearer | Create a conversation |
| GET | `/conversations/{id}` | Bearer | Conversation + messages |
| GET | `/conversations/{id}/messages` | Bearer | Messages only |
| DELETE | `/conversations/{id}` | Bearer | Delete a conversation |
| GET | `/chat/providers` | Bearer | Configured AI provider + status |
| POST | `/chat/completions` | Bearer | Streaming reply (SSE) |
| POST | `/live/ticket` | Bearer | Short-lived ticket for the live-voice socket |
| WS | `/live/session` | ticket | Gemini Live relay (browser to model) |
| POST | `/devices/pairing/start` | – | Companion starts pairing, gets a code |
| GET | `/devices/pairing/{id}` | – | Companion polls pairing status |
| POST | `/devices/pairing/approve` | Bearer | Approve a code, issues a device token |
| GET | `/devices` | Bearer | List paired devices |
| PATCH | `/devices/{id}` | Bearer | Rename / change permissions |
| DELETE | `/devices/{id}` | Bearer | Revoke a device |
| POST | `/devices/{id}/command` | Bearer | Send an allowlisted command |
| GET | `/devices/catalog` | Bearer | The allowlist (for the web command form) |
| GET | `/devices/actions` | Bearer | Action history |
| WS | `/devices/companion` | token | Desktop companion control socket |

`POST /chat/completions` streams `data: {json}` events:
`{"type":"delta","text":...}`, then `{"type":"done","conversation_id":...}`,
then `data: [DONE]`.

## AI provider

`app/services/ai.py` defines the `AIProvider` abstraction. Gemini is the only
production provider wired today; `build_provider()` raises
`ProviderNotConfigured` (HTTP 503) when no key is set — it never fabricates
output. Add providers (e.g. a local LLM) by implementing `stream()`.

## Database migrations

```bash
python -m alembic revision --autogenerate -m "message"   # after model changes
python -m alembic upgrade head
python -m alembic downgrade -1
```

## Production

Set at minimum:

```
ENVIRONMENT=production
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/mark_liv
JWT_SECRET=<48-byte urlsafe random>
CORS_ORIGINS=https://your-web-app
GEMINI_API_KEY=...
EMAIL_BACKEND=smtp
SMTP_* / WEB_APP_URL=...
```

In production, startup requires a `JWT_SECRET` of at least 32 characters, a
`postgresql+asyncpg://` `DATABASE_URL`, non-wildcard `CORS_ORIGINS`, and
`EMAIL_BACKEND=smtp` with `SMTP_HOST` and a non-local `SMTP_FROM` address. SMTP
username/password must be configured together. `console` email and SQLite
remain development/test options only.

## Docker

```bash
docker compose up --build      # from the repository root
```

Starts PostgreSQL, the API, and the web app; migrations run automatically on
start. The API waits for a healthy database, and the web app waits for a healthy
API. See `docs/DEPLOYMENT.md` for the full guide (secrets, TLS, reverse proxy).
