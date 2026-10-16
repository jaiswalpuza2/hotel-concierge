# Deployment — Railway (via Docker Hub images)

Validated locally on 2026-10-16: both production images boot, `/health` returns
`db: ok`, the WebSocket chat streams real Groq answers with RAG sources, and the
admin login works through the Next.js server proxy.

Why this route: Railway's GitHub builder cannot read `../knowledge_base` from
`backend/Dockerfile` (each service gets its own folder as the build context), and
Railway does not pass Docker build args. Building the images locally and pushing
them to Docker Hub avoids both problems and gives you the exact image you tested.

---

## 1. One-time accounts

1. **Railway** — https://railway.app → *Login with GitHub* → authorize. A payment
   card is required even on the usage-based plan.
2. **Docker Hub** — https://hub.docker.com → sign up with the same GitHub account.
   Profile → **Personal access tokens** → *New Access Token* → name it `deploy`,
   copy it immediately.
3. Open https://railway.app/new/private and create a **private** repo, **no
   README, no .gitignore** (we push our own).

## 2. Publish the code (PowerShell, from the repo root)

```powershell
git init
git add .
git commit -m "Hotel multi-agent concierge 1.1.0"
git branch -M main
git remote add origin https://github.com/<your-user>/hotel-concierge.git
git push -u origin main
```

`.env`, `frontend/.env`, `.env.prod`, `node_modules`, `.venv` and `.next` are
already excluded by `.gitignore`. Verify with `git status` before pushing.

## 3. Postgres with pgvector

1. Railway → your project → **New → Database → Postgres**.
2. Open the new service → **Variables → Raw Variables** → add:
   ```
   POSTGRES_DB=hoteldb
   ```
   Railway recreates the container; DB name becomes `hoteldb`.
3. Service → **Shell** tab, then:
   ```bash
   psql -U "$POSTGRES_USER" -d hoteldb -c "create extension if not exists vector;"
   psql -U "$POSTGRES_USER" -d hoteldb -c "select extname from pg_extension;"
   ```
   `vector` must be listed. (If `create extension` errors, Railway's image lacks
   pgvector — use the Supabase option in the appendix.)

## 4. Build and push the images (PowerShell)

`$` is PowerShell syntax — keep the `"$"` quoting exactly as written.

```powershell
docker login -u <dockerhub-user>          # paste the access token
cd "<repo root>"

docker build -f Dockerfile.railway -t <dockerhub-user>/hh-backend:latest .
docker push <dockerhub-user>/hh-backend:latest

docker build -f frontend/Dockerfile --target production -t <dockerhub-user>/hh-frontend:latest ./frontend
docker push <dockerhub-user>/hh-frontend:latest
```

The frontend image is built **without** `NEXT_PUBLIC_*` args, so it keeps the
`http://localhost:8000` / `ws://localhost:8000` defaults and the container
entrypoint rewrites them at start-up from the variables you set in step 5 —
this is what lets you change the backend domain without rebuilding.

## 5. Deploy the backend

1. Railway → **New → Service → Deploy Image** → use the **private** networking
   checkbox off → `dockerhub-user/hh-backend:latest`.
2. Service → **Settings → Networking → Generate Domain** (e.g.
   `hotel-api.up.railway.app`).
3. **Variables** → *Raw Variables*. Our app requires the `postgresql+asyncpg://`
   scheme, so do **not** use Railway's plain `DATABASE_URL` reference — build the
   URL from the Postgres variables instead (Railway substitutes them at deploy
   time; pick the `Postgres.` form from the variable picker, it is the one the
   dashboard offers):
   ```
   DB_URL=postgresql+asyncpg://${{ Postgres.POSTGRES_USER }}:${{ Postgres.POSTGRES_PASSWORD }}@${{ Postgres.POSTGRES_HOST }}:${{ Postgres.POSTGRES_PORT }}/${{ Postgres.POSTGRES_DB }}
   ```
   If the picker only offers the `PG*` names, the equivalent is
   `postgresql+asyncpg://${{ Postgres.PGUSER }}:${{ Postgres.PGPASSWORD }}@${{ Postgres.PGHOST }}:${{ Postgres.PGPORT }}/${{ Postgres.PGDATABASE }}`.
   Keep the Postgres service **private** (no Public Networking) — only the API
   needs to reach it.
   ```
   APP_ENV=production
   LOG_LEVEL=INFO
   LOG_FORMAT=json
   KNOWLEDGE_BASE_PATH=/app/knowledge_base
   JWT_SECRET_KEY=<paste a fresh 64-hex secret>
   LLM_PROVIDER=openai
   LLM_MODEL=openai/gpt-oss-20b
   LLM_API_KEY=<Groq key>
   LLM_BASE_URL=https://api.groq.com/openai/v1
   LLM_TEMPERATURE=0.2
   LLM_MAX_TOKENS=512
   EMBEDDING_PROVIDER=hashing
   RETRIEVAL_TOP_K=3
   RETRIEVAL_CONFIDENCE_THRESHOLD=0.25
   SMS_PROVIDER=mock
   EMAIL_PROVIDER=smtp
   SMTP_HOST=smtp.resend.com
   SMTP_PORT=587
   SMTP_USERNAME=resend
   SMTP_PASSWORD=<Resend key>
   SMTP_FROM=onboarding@resend.dev
   HANDOFF_PROVIDER=mock
   CORS_ORIGINS=["https://<frontend-domain>.up.railway.app","http://localhost:3000"]
   DASHBOARD_URL=https://<frontend-domain>.up.railway.app/admin/handoffs
   ```
   `CORS_ORIGINS` is the WebSocket origin allowlist too (`app/api/ws/chat.py`).
   The frontend domain is created in step 6 — come back and update it, then
   redeploy.
4. **Settings → Deploy → Custom Start Command**:
   ```
   alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips "*"
   ```
   Never add `python scripts/seed_db.py` here — it TRUNCATEs every table and
   would erase live bookings on each restart.
5. Deploy, then open `https://<backend-domain>/health` →
   `{"status":"ok","db":"ok"}`.

## 6. Deploy the frontend

1. **New → Service → Deploy Image** → `dockerhub-user/hh-frontend:latest`.
2. **Variables**:
   ```
   NEXT_PUBLIC_API_URL=https://<backend-domain>.up.railway.app
   NEXT_PUBLIC_WS_URL=wss://<backend-domain>.up.railway.app
   API_INTERNAL_URL=http://<backend-domain>.up.railway.app
   ```
3. **Settings → Networking → Generate Domain**.
4. Go back to the backend and add `https://<frontend-domain>.up.railway.app` to
   `CORS_ORIGINS`, then **Redeploy** the backend.

## 7. Seed and index once

Backend service → **Shell**:
```bash
python scripts/seed_db.py
python scripts/ingest_kb.py
```
`ingest_kb.py` is idempotent (skips already-indexed files). Expect ~12 documents
indexed; verify at `/admin/documents`.

## 8. Verify live

1. `https://<backend-domain>/health` → `db: ok`.
2. `https://<frontend-domain>/` → landing page animations.
3. `/chat` → status **Connected**, ask "What time is check-in?" → streamed answer
   plus SOURCES chips.
4. Book a room end-to-end, then sign in at `/admin/login`
   (`admin@hotel.local` / the seeded password) and check Bookings.
5. Resend: real emails only reach the address on your Resend account until you
   verify your own domain.

## Notes / limits

- Railway's free/trial credit is limited; the services sleep only on hobby plan
  inactivity, but stopped services do release their public domain routing.
- WebSocket works over `wss://` on `*.up.railway.app`.
- Groq's free tier is 8k tokens/min account-wide — keep `MAX_TOKENS=512` and
  `TOP_K=3`; the backend now honours `retry-after` on 429s.
- Rebuild + push, then Railway → backend → **Redeploy**, for every code change
  (Railway does not watch Docker Hub tags automatically).

## Appendix — alternative: deploy from GitHub

Set each service's **Root Directory** and Dockerfile explicitly:
backend → root directory `backend`, Dockerfile `Dockerfile` — but then the image
has no `/knowledge_base`; either commit a copy inside `backend/` or switch the
backend service to `Dockerfile.railway` with root directory = repo root
(`RAILWAY_DOCKERFILE_PATH=Dockerfile.railway`). The frontend service works from
root directory `frontend` with `frontend/Dockerfile`, target `production`.
`Dockerfile.railway` exists for exactly this path.
