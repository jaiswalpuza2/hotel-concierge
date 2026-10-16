# =============================================================================
# Frontend Dockerfile — multi-stage
# Stage: development  → Next.js dev server (used by docker-compose)
# Stage: builder      → production build
# Stage: production   → minimal node:alpine serve
# =============================================================================

FROM node:20-alpine AS base
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
FROM base AS deps
COPY package.json package-lock.json* ./
# `npm ci` is stricter than the lockfile's platform-optional deps allow
# (it rejects the Windows-resolved @emnapi tree on Alpine), so use a plain
# install here; the lockfile is still honoured for all pinned versions.
RUN npm install --no-audit --no-fund

# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------
FROM base AS development
COPY --from=deps /app/node_modules ./node_modules
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev"]

# ---------------------------------------------------------------------------
# Production builder
# ---------------------------------------------------------------------------
FROM base AS builder
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# NEXT_PUBLIC_* values are inlined into the client bundle at build time.
# Pass them with: docker build --build-arg NEXT_PUBLIC_API_URL=... (target production)
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_WS_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL
RUN npm run build

# ---------------------------------------------------------------------------
# Production runtime
# ---------------------------------------------------------------------------
FROM node:20-alpine AS production

RUN addgroup --gid 1001 nodejs && adduser --uid 1001 --ingroup nodejs --disabled-password nextjs

WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

# If the image was built without --build-arg URLs, inject them at container
# start instead (sed into the static bundle). Built-in URLs are left untouched.
RUN printf '#!/bin/sh\nif [ -n "$NEXT_PUBLIC_API_URL" ]; then\n  grep -rlF "http://localhost:8000" ./.next/static >/tmp/f 2>/dev/null || true\n  while IFS= read -r f; do sed -i "s#http://localhost:8000#$NEXT_PUBLIC_API_URL#g" "$f"; done < /tmp/f\nfi\nif [ -n "$NEXT_PUBLIC_WS_URL" ]; then\n  grep -rlF "ws://localhost:8000" ./.next/static >/tmp/f 2>/dev/null || true\n  while IFS= read -r f; do sed -i "s#ws://localhost:8000#$NEXT_PUBLIC_WS_URL#g" "$f"; done < /tmp/f\nfi\nexec node server.js\n' > /app/docker-entrypoint.sh && chmod +x /app/docker-entrypoint.sh

USER nextjs
EXPOSE 3000
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["node", "server.js"]
