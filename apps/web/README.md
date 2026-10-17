# MARK LIV Web (`apps/web`)

Next.js (App Router) + TypeScript + Tailwind + Framer Motion + Lucide front end for the
MARK LIV platform. Talks to the FastAPI backend in `services/api`.

## Architecture: BFF + httpOnly cookies

The browser **never** holds a token and **never** talks to the backend directly:

```
Browser ──same-origin──► Next route handlers ──bearer──► FastAPI (services/api)
                          (/api/auth/*, /api/proxy/*)
```

- `/api/auth/login`, `/register` → call the backend, then store the access + refresh JWTs
  in **httpOnly, SameSite=Lax** cookies (Secure in production).
- `/api/auth/me` → returns the current user, transparently refreshing an expired access
  token and re-issuing cookies.
- `/api/proxy/[...path]` → catch-all proxy that attaches the bearer header server-side and
  **streams** the response back, so SSE chat responses pass through unbuffered.
- `/api/auth/logout` → clears the cookies.

Because tokens live in httpOnly cookies, an XSS bug cannot read them. `API_BASE_URL` is a
server-only variable, so the backend origin and any provider keys stay out of the client
bundle.

## Requirements

- Node.js 20+ (developed on Node 24)
- A running backend (`services/api`) — see its README

## Development

```bash
cd apps/web
cp .env.example .env.local     # set API_BASE_URL if not http://localhost:8080
npm install
npm run dev                    # http://localhost:3000
```

Start the backend first:

```bash
cd services/api
cp .env.example .env
python -m alembic upgrade head
uvicorn app.main:app --reload --port 8080
```

## Scripts

| Script | Purpose |
|---|---|
| `npm run dev` | Dev server |
| `npm run build` | Production build |
| `npm run start` | Serve the production build |
| `npm run lint` | ESLint (next/core-web-vitals + next/typescript) |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run format` | Prettier |

## Structure

```
src/
├── app/
│   ├── page.tsx                 # marketing landing
│   ├── (auth)/                  # login, register, forgot/reset password
│   ├── (app)/                   # protected shell: chat, voice, devices, settings, account
│   └── api/                     # BFF: auth handlers + backend proxy
├── components/                  # shell, chat UI, shadcn-style primitives
└── lib/                         # api client, server-auth (cookies), types, utils
```

## Status

Implemented in the application and backed by FastAPI routes: registration/login/logout,
password reset, protected pages, streaming chat with persisted conversation history,
provider status, live voice, device pairing/management, and the desktop command relay.
The desktop relay uses a server and client allowlist; sensitive power actions are
denied on the desktop unless a local confirmation callback is configured.
The companion currently requires a local `companion` configuration block; the
desktop has no GUI pairing toggle yet.

The web production build and TypeScript check are the local deployment checks. Gemini
calls, real browser microphone/speaker behavior, live TLS WebSockets, and an end-to-end
paired desktop session still need credentials, supported hardware, and a deployed API;
they are not verified by the build.

## Deploy (Vercel)

Set `API_BASE_URL` to the HTTPS FastAPI origin in the Vercel project settings. For browser
live voice, also set `NEXT_PUBLIC_API_BASE_URL` and `NEXT_PUBLIC_API_WS_URL` (the latter
must use `wss://`). `NEXT_PUBLIC_*` values are baked into the client build, so redeploy
after changing them. Deploy the API to persistent hosting that supports WebSockets, not a
serverless function. See [`docs/DEPLOYMENT.md`](../../docs/DEPLOYMENT.md) for backend,
database, mail, TLS, and environment-variable requirements.
