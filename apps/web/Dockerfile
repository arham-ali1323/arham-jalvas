# MARK LIV web app (Next.js) — production image.
#
# Multi-stage so the runtime layer carries only the standalone server and the
# static assets, not the toolchain or node_modules.
#
# NEXT_PUBLIC_* values are inlined into the client bundle at BUILD time, so they
# arrive as build args (see docker-compose.yml). Anything that must change at
# runtime (API_BASE_URL, the server-side proxy target) is a normal env var.

FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ARG NEXT_PUBLIC_API_WS_URL
ARG NEXT_PUBLIC_API_BASE_URL
ARG NEXT_PUBLIC_APP_NAME
ENV NEXT_PUBLIC_API_WS_URL=${NEXT_PUBLIC_API_WS_URL}
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
ENV NEXT_PUBLIC_APP_NAME=${NEXT_PUBLIC_APP_NAME}
ENV NEXT_OUTPUT=standalone
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000

CMD ["node", "server.js"]
