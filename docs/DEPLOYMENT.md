# Deploying MARK LIV

MARK LIV runs as three cooperating services:

| Service | Directory | Role |
|---|---|---|
| **db** | — | PostgreSQL 16 — users, conversations, paired devices, action history |
| **api** | `services/api` | FastAPI + WebSockets — auth, chat (SSE), live-voice relay, device control |
| **web** | `apps/web` | Next.js — the browser UI; also proxies REST to the API |

The desktop app (`main.py`) is **not** part of this stack. It is installed on the
user's own machine (see Phase 7 packaging) and talks to the API as a paired
device.

---

## 1. Quick start (single host)

From the repository root:

```bash
# 1. Copy the Compose template and replace both placeholders.
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # use for JWT_SECRET
# Use a separate high-entropy value for POSTGRES_PASSWORD.

# 2. Build and run.
docker compose up --build
```

PowerShell users can copy the template with `Copy-Item .env.example .env`.
`POSTGRES_PASSWORD` and `JWT_SECRET` are required; Compose will refuse to start
without them. Do not commit `.env`.

Then open <http://localhost:3000>. The API is at <http://localhost:8080>
(`/health`, `/health/ready`, `/docs`).

On first start the API container runs `alembic upgrade head` before serving, so
the schema is always current.

### Desktop pairing status

The pairing protocol and web device-management routes exist, but the desktop
does not yet have a settings control to configure or enable the companion.
Currently it starts only when its local `config/api_keys.json` contains a
`companion` object with `enabled: true` and `api_base_url` set to the API origin.
The pairing code is then shown in the desktop log and is approved from the
signed-in Devices page. Do not copy a device token into source control.

Sensitive power actions require the web permission scope and a local desktop
confirmation callback. The normal Qt app does not wire that callback, so those
actions are safely denied there; the standalone companion entry point has a
console prompt. A user-facing desktop confirmation flow remains before those
actions can be offered as working features.

### Verify it came up

```bash
curl -fsS localhost:8080/health/ready   # {"status":"ready"} once the DB answers
```

---

## 2. Configuration

### Backend (`services/api`)

Copy `services/api/.env.example` to `.env` for non-Docker runs. The compose file
passes these through. The ones that matter:

| Variable | Notes |
|---|---|
| `JWT_SECRET` | **Required in production; at least 32 characters.** Generate a random value. Rotating it logs everyone out. |
| `DATABASE_URL` | `postgresql+asyncpg://…` in Docker; SQLite is the dev default. |
| `ENVIRONMENT` | In production, requires a PostgreSQL async URL, `JWT_SECRET`, SMTP email, and non-wildcard CORS origins. |
| `CORS_ORIGINS` | Comma-separated browser origins. **No wildcard in production.** |
| `GEMINI_API_KEY` | Server-side only; browsers never receive it (they get a short-lived WebSocket ticket). |
| `WEB_APP_URL` | Where password-reset links point, and what a pairing code is verified against. |
| `EMAIL_BACKEND` | `console` (dev) or `smtp` (production, with the `SMTP_*` block). |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_USE_TLS` | SMTP delivery configuration. Use a non-`.local` sender accepted by your mail provider; username/password must either both be set or both be blank. |

### Web (`apps/web`)

`NEXT_PUBLIC_*` values are **inlined into the client bundle at build time**, so
they are passed as Docker build args, not runtime environment:

| Build arg | Meaning |
|---|---|
| `NEXT_PUBLIC_API_WS_URL` | Browser-reachable WebSocket origin for live voice (`wss://…` in production). |
| `NEXT_PUBLIC_API_BASE_URL` | Browser-reachable API origin. |
| `NEXT_PUBLIC_APP_NAME` | Display name. |

Runtime-only (server-side proxy target, never sent to the browser):

| Variable | Meaning |
|---|---|
| `API_BASE_URL` | In-container API address, e.g. `http://api:8080`. |

To change a public value you must **rebuild** the web image — restarting is not
enough.

## 3. Deploying the web app to Vercel

Import the repository into Vercel and set the project root to `apps/web`.
Vercel detects Next.js; use `npm ci` for installation and `npm run build` for
the production build. Set these project environment variables:

| Variable | Value |
|---|---|
| `API_BASE_URL` | HTTPS URL of the persistent FastAPI service, e.g. `https://api.example.com`. Server-only; required at runtime. |
| `NEXT_PUBLIC_API_BASE_URL` | Browser-reachable HTTPS API URL. |
| `NEXT_PUBLIC_API_WS_URL` | Browser-reachable WSS API origin, e.g. `wss://api.example.com`; required for browser live voice. |
| `NEXT_PUBLIC_APP_NAME` | Optional display name; defaults to `MARK LIV`. |

The `NEXT_PUBLIC_*` values are compiled into the browser bundle, so set them
for the production environment before deploying and redeploy after changing
them. Never set `GEMINI_API_KEY`, `JWT_SECRET`, database credentials, or SMTP
credentials as `NEXT_PUBLIC_*` values. Add each Vercel production/preview
website origin to the API's `CORS_ORIGINS` if the browser connects directly to
the API WebSocket.

Vercel hosts the web tier only. Deploy `services/api` and PostgreSQL separately
to persistent infrastructure that supports long-running FastAPI processes and
WebSockets; do not put the backend in a Vercel serverless function. Keep the API
at one worker/replica unless its in-memory pairing, socket, ticket, and rate
limit stores are moved to shared storage. Confirm `/health/ready` returns 200
and test both `wss://…/live/session` and `wss://…/devices/companion` through the
provider's TLS proxy before inviting users.

---

## 4. Putting it behind TLS (required in production)

The device companion sends its credential in the WebSocket URL query string (the
WebSocket upgrade cannot carry an `Authorization` header), and the live-voice
socket carries a ticket the same way. Both must therefore run over TLS so they
are never in the clear. Terminate TLS at a reverse proxy and forward to the two
containers.

### Caddy (simplest — automatic certificates)

```caddyfile
app.example.com {
    reverse_proxy web:3000
}
api.example.com {
    reverse_proxy api:8080
}
```

Then set, in the compose `.env`:

```
CORS_ORIGINS=https://app.example.com
WEB_APP_URL=https://app.example.com
NEXT_PUBLIC_API_BASE_URL=https://api.example.com
NEXT_PUBLIC_API_WS_URL=wss://api.example.com
```

and rebuild the web image so the new public URLs are baked in.

### nginx (equivalent)

```nginx
server {
    listen 443 ssl;
    server_name api.example.com;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;      # live voice + device socket
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 3600s;                     # long-lived sockets
    }
}
```

The `Upgrade`/`Connection` headers and a long `proxy_read_timeout` are what keep
the WebSockets alive; without them they close immediately.

---

## 5. Scaling caveat — run the API as a **single worker**

Several features keep short-lived state **in process memory** on purpose, to
avoid a Redis dependency for a small deployment:

- pairing sessions (`PairingStore`)
- live device sockets (`DeviceHub`)
- live-voice tickets and the per-IP connect rate limit

Consequences:

- Run **one** uvicorn worker (`uvicorn app.main:app`, no `--workers N`). The
  Docker image already does.
- Do **not** scale the `api` service horizontally behind a load balancer that
  spreads one client's requests across replicas, or a companion's socket and the
  web command that targets it can land on different processes.

If you outgrow this, the fix is to move those four stores to Redis pub/sub and a
shared ticket store; the interfaces (`DeviceHub`, `PairingStore`) are already
isolated to make that swap contained.

---

## 6. Migrations

Run automatically on container start. To run them by hand:

```bash
docker compose exec api alembic upgrade head
docker compose exec api alembic current
```

After a model change, generate a migration locally and commit it:

```bash
cd services/api
python -m alembic revision --autogenerate -m "what changed"
python -m alembic upgrade head
python -m alembic check     # fails if the migration does not match the models
```

CI should run `alembic check` to catch drift.

---

## 7. Backups

Everything durable is in PostgreSQL. Back up the `pgdata` volume:

```bash
docker compose exec db pg_dump -U markliv mark_liv | gzip > backup-$(date +%F).sql.gz
```

The Gemini key, `.env`, and per-plugin credentials live only on hosts and in the
desktop config — back them up separately; they are never in the database.

---

## 8. Updating

```bash
git pull
docker compose build
docker compose up -d
```

Migrations run on the new API container's start. For the web app, `NEXT_PUBLIC_*`
changes require the rebuild above (which `build` performs).

---

## 9. Health & troubleshooting

| Symptom | Check |
|---|---|
| API container `unhealthy` | `docker compose logs api`; `/health/ready` returns 503 until the DB is reachable. |
| Live voice connects then drops | Reverse proxy is stripping the `Upgrade` header or closing idle sockets — see §3. |
| Browser calls fail with CORS | `CORS_ORIGINS` does not include the exact web origin (scheme + host + port). |
| Pairing code rejected | Codes expire after a few minutes; and `WEB_APP_URL` should match where the user is approving. |
| Device shows offline after connecting | Only one API worker can hold the socket — see §4. |
