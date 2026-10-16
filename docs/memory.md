# Project Memory — Living Document
## Autonomous Multi-Agent Local Business Concierge
### Demo Instance: Himalayan Heritage Hotel

**Last Updated:** 2026-10-16
**Current Phase:** All phases implemented (0-13). Environment verification complete (see "Verification status").
**Current Task:** None — verified end-to-end on this machine (Docker stack + mock providers). Real LLM/STT/TTS keys still optional future work.

---

## Completion summary (handover)

| Phase | Status | Notes |
|---|---|---|
| 0-3 Scaffold, FastAPI core, DB + Alembic + seed, JWT auth | Done (Kiro) | Fixed: mojibake/BOM in files, CORS middleware order, default JWT secret guard |
| 4 RAG ingestion + retrieval | Done, **bugs fixed** | PDF loader read page count after `close()`; pgvector SQL used `:x::vector` casts (bind-name parsing); ingestion held one transaction so "processing" was never visible; OpenAI embedder ignored `dimensions`. Added offline `hashing` embedder + KnowledgeService + `kb_loader` |
| 5 Tools + mock DB | Done | 10 tools, signed quotes, confirmation flags, restaurant/service/conversation/notification repos |
| 6 LangGraph agents | Done | Declarative `agents/graph_spec.py` compiled by `agents/graph.py`; tested end-to-end with the same spec |
| 7 Bilingual + BS dates | Done | `utils/nepali_text.py`, `utils/bikram_sambat.py` (BS 2080-2084) |
| 8 Notifications | Done | Sparrow SMS, SMTP, mock; EN/NE/Roman templates; delivery log |
| 9 Human handoff | Done | Triggers, ticket, Telegram/Slack/mock alert, manager reply push, resolve/resume |
| 10 WebSocket + voice | Done | `/ws/chat` protocol in `api/ws/chat.py`; Whisper STT, OpenAI/Google/mock TTS; browser STT fallback |
| 11 Customer chat UI | Done | Next.js App Router, streaming text, EN/NE toggle, citations, mic, Web Audio playback |
| 12 Admin dashboard | Done | Documents, handoff inbox, conversations, bookings, stats |
| 13 Tests/Docker/hardening | Partly verified | See below |

## Verification status (verified 2026-10-16 on the dev machine)

Ran locally (Docker stack: concierge_postgres :5433, concierge_api :8000, concierge_frontend dev :3000, production build :3100; offline providers `LLM_PROVIDER=mock`, `EMBEDDING_PROVIDER=hashing`, STT/TTS none):
- `alembic upgrade head` + `seed_db.py` + `ingest_kb.py` all succeed (12 documents indexed, 49 bookings).
- `scripts/smoke_test.py` 18/18; pytest unit 123/123; integration 38/38 (161 total).
- Browser E2E: streaming WS chat, guarded booking (availability -> details -> "yes" -> HH- reference persisted), unknown-question handoff (HT- ticket), staff reply pushed live, resolve returns control to AI. All admin pages (stats, documents, handoffs, bookings, conversations) render with live data.
- `next build` clean (14 routes); production bundle verified on :3100.

Bugs found and fixed during verification:
- Alembic/env.py and config.py did not load repo-root `.env` (fell back to wrong port 5432).
- Cartesian-product row count in `booking_repo.list_all` / `handoff_repo` (wrong `total` in admin lists).
- Dev-mode reply loss: `message_chunk` updater mutated `streamingId` ref inside itself — React StrictMode double-invocation discarded the appended bubble. Updaters made pure.
- WS hook hardened: half-open detection via ping/pong watchdog; handlers detached on cleanup to stop rogue StrictMode reconnects.
- `test_decode_tampered_token_raises` flaky (last base64url char has padding bits) — tampers first signature char now.
- CORS_ORIGINS lacked :3100 for production preview.

Animation layer added (globals.css keyframes + utility classes, `prefers-reduced-motion` guard): landing hero/feature stagger, chat slide-in bubbles, ping-ring status/voice, citation chip scale-in, admin card stagger + skeletons, hover lifts.

## Key decisions added in this session

1. **No LangChain.** LLM providers are thin httpx clients (`app/llm/`) with a neutral message/tool format. Removes the langchain version-pin conflict and makes swapping providers trivial.
2. **Handoff pause/resume uses DB state + checkpointer, not `interrupt()`.** Conversation status `handed_off` + open ticket drive the `human_relay` route; manager replies are pushed over WebSocket; `resolve` returns control to the AI. Same behaviour, fewer version-sensitive APIs.
3. **Graph spec is data** (`GraphSpec`) so the exact routing is unit-testable without LangGraph.
4. **Booking safety is enforced in code, not only in prompts:** `book_room` requires a signed, expiring `quote_id` (HMAC) produced by the availability/price tools and `user_confirmed=true`; cancel/status need reference + phone.
5. **Checkpointer falls back to memory** if psycopg/Postgres async is unavailable (e.g. Windows Proactor loop). Use `python run.py` on Windows.
6. **Retrieval threshold default lowered 0.6 -> 0.35** (0.6 rejects many valid matches for multilingual-mpnet); tune with real questions.
7. **Dependencies:** `asyncpg>=0.30` (0.29 has no Python 3.13 wheels), removed langchain/openai/pgvector packages, added `langgraph>=0.4`, `langgraph-checkpoint-postgres`, `psycopg[binary,pool]`.
8. **Streaming:** replies are streamed to the UI in small chunks after generation (typing effect); true token streaming from the provider is a possible future upgrade.

## Known limitations / next steps

- Bikram Sambat table covers 2080-2084 and is NOT verified against the official panchang month by month.
- Festival multipliers in the seed are approximate.
- WebSocket push registry is single-process (use Redis pub/sub for multiple workers).
- Only the hotel has live tools; other business profiles are knowledge-base-only.
- Add per-session rate limiting and PII retention rules before public launch.

---

## Earlier status log (Kiro, Phases 0-4)


## Phase 0 status

**P0-T1 COMPLETE.** All scaffold files created:

- `docker-compose.yml` — postgres (pgvector/pgvector:pg16), api, frontend services with healthchecks ✅
- `backend/pyproject.toml` — all deps pinned, ruff/mypy/pytest fully configured ✅
- `backend/alembic.ini` — Alembic config, DB_URL read from env ✅
- `backend/alembic/env.py` — async-aware Alembic env, imports all model modules ✅
- `backend/app/main.py` — FastAPI app factory with lifespan and CORS ✅
- `backend/app/config.py` — Pydantic Settings, all env vars, lru_cache ✅
- `backend/app/db/base.py` — AsyncEngine, session factory, Base declarative ✅
- `backend/Dockerfile` — multi-stage (development + production) ✅
- `frontend/Dockerfile` — multi-stage (development + production) ✅
- `.env.example` — all variables with descriptions ✅
- `.gitignore` — secrets, caches, node_modules, uploads ✅
- `Makefile` — dev, stop, migrate, seed, lint, format, typecheck, test, test-cov, ci, clean ✅
- `README.md` — quick-start, commands, config table, tech stack ✅
- All backend package `__init__.py` files ✅
- All directory structure created ✅

**Note:** Docker daemon is not running in this environment — the `docker-compose up postgres` verification step requires Docker Desktop to be started by the user. All Python files verified with syntax check (Python 3.13 available; code uses 3.12-compatible syntax).

**Awaiting user confirmation before starting P0-T2.**

---

## Versions (Pinned)

| Component | Version | Notes |
|-----------|---------|-------|
| Python | 3.12 | Required minimum |
| FastAPI | 0.115.x | Latest stable at doc time |
| SQLAlchemy | 2.0.x | Async ORM |
| asyncpg | 0.29.x | Async PostgreSQL driver |
| Alembic | 1.13.x | DB migrations |
| pgvector | 0.3.x | Python client; DB extension: 0.7.x |
| LangGraph | 0.2.x | Multi-agent orchestration |
| LangChain | 0.3.x | LLM abstraction layer |
| Pydantic | 2.8.x | Settings + data validation |
| structlog | 24.x | Structured logging |
| ruff | 0.6.x | Linter + formatter |
| mypy | 1.11.x | Type checker |
| pytest | 8.x | Test framework |
| pytest-asyncio | 0.24.x | Async test support |
| httpx | 0.27.x | Async HTTP client |
| python-jose | 3.3.x | JWT library |
| bcrypt | 4.x | Password hashing |
| PyMuPDF (fitz) | 1.24.x | PDF loader |
| sentence-transformers | 3.x | Multilingual embeddings |
| PostgreSQL | 16 | DB server |
| pgvector extension | 0.7.x | Vector similarity search |
| Next.js | 14.x (App Router) | Frontend framework |
| TypeScript | 5.x | Strict mode |
| Tailwind CSS | 3.x | Styling |
| Node.js | 20 LTS | Frontend runtime |

---

## Environment Variables (Complete List)

All must be defined in `.env`; `.env.example` has placeholders and descriptions.

### Database
```
DB_URL=postgresql+asyncpg://postgres:password@localhost:5432/hoteldb
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
```

### JWT Auth
```
JWT_SECRET_KEY=<generate with: openssl rand -hex 32>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
```

### LLM Provider
```
LLM_PROVIDER=openai          # openai | anthropic | ollama
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=<your key>
LLM_BASE_URL=                # optional, for Ollama or custom endpoints
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=1024
```

### Embedding
```
EMBEDDING_PROVIDER=sentence_transformer   # sentence_transformer | openai
EMBEDDING_MODEL=paraphrase-multilingual-mpnet-base-v2
EMBEDDING_DIMENSIONS=768
OPENAI_EMBEDDING_MODEL=text-embedding-3-small   # used if EMBEDDING_PROVIDER=openai
```

### RAG
```
RETRIEVAL_TOP_K=5
RETRIEVAL_CONFIDENCE_THRESHOLD=0.6
MAX_RETRIEVAL_RETRIES=2
MAX_TOOL_RETRIES=2
RERANKER_ENABLED=false
RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
```

### SMS Notifications
```
SMS_PROVIDER=mock            # mock | sparrow
SMS_SPARROW_TOKEN=<token>
SMS_SPARROW_FROM=HimalHotel
```

### Email Notifications
```
EMAIL_PROVIDER=mock          # mock | smtp
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=<email>
SMTP_PASSWORD=<password>
SMTP_FROM=noreply@himalayan-hotel.com
```

### Handoff Alerts
```
HANDOFF_PROVIDER=mock        # mock | telegram | slack
TELEGRAM_BOT_TOKEN=<token>
TELEGRAM_CHAT_ID=<chat_id>
SLACK_WEBHOOK_URL=<url>
```

### Voice
```
STT_PROVIDER=whisper         # whisper | google
TTS_PROVIDER=google          # google | openai
OPENAI_WHISPER_API_KEY=<key>
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
GOOGLE_TTS_VOICE_NE=ne-NP-Standard-A
GOOGLE_TTS_VOICE_EN=en-US-Standard-D
```

### Application
```
APP_ENV=development          # development | staging | production
LOG_LEVEL=DEBUG              # DEBUG | INFO | WARNING | ERROR
LOG_FORMAT=json              # json | text
CORS_ORIGINS=http://localhost:3000,http://localhost:8000
MAX_FILE_UPLOAD_BYTES=20971520
RATE_LIMIT_PER_MINUTE=60
```

### Business Config
```
BUSINESS_NAME=Himalayan Heritage Hotel
BUSINESS_TYPE=hotel
BUSINESS_LOCATION=Itahari, Sudurpurba Province, Nepal
KNOWLEDGE_BASE_PATH=knowledge_base/
```

### Frontend
```
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

---

## Key Decisions

| # | Decision | Reason | Date |
|---|----------|--------|------|
| 1 | Use pgvector + PostgreSQL for both relational data and vector embeddings | Reduces infrastructure complexity; single DB to manage; pgvector performance sufficient for hotel-scale document count (< 100K chunks) | 2026-10-12 |
| 2 | `paraphrase-multilingual-mpnet-base-v2` as default embedding model | Supports Nepali; runs locally without API key; 768 dimensions; well-tested on South Asian languages | 2026-10-12 |
| 3 | LangGraph with Postgres checkpointer (not Redis) | Keeps state durable, inspectable, and in the same DB; avoids adding a second stateful service in Phase 1 | 2026-10-12 |
| 4 | FastAPI BackgroundTasks for notifications in Phase 1 (Celery + Redis in Phase 2) | Simpler infrastructure for the demo; upgrade path is documented and the interface is stable | 2026-10-12 |
| 5 | All monetary amounts stored as INTEGER NPR (not sub-rupee) | Hotel pricing in Nepal uses whole rupees; avoids floating-point issues | 2026-10-12 |
| 6 | STT/TTS behind provider interfaces; document Nepali quality tradeoffs | No single STT provider has excellent Nepali support; Google Cloud STT is best current option but quality for rural/accented Nepali may be poor | 2026-10-12 |
| 7 | Language detection uses Unicode range heuristic (not an ML classifier) | Devanagari Unicode is a reliable signal; fast and dependency-free; Romanized Nepali detected via keyword list | 2026-10-12 |
| 8 | Business-type config via YAML + env vars, not code | Core agent logic, graph, and tools are business-agnostic; swapping to hospital/co-op requires only config change | 2026-10-12 |
| 9 | JWT stored in HTTP-only cookie (refresh) + memory (access) | Prevents XSS access to refresh token; access token expiry is short enough that memory storage is acceptable | 2026-10-12 |
| 10 | Bikram Sambat converter uses static calendar data table (not algorithm) | The Nepali calendar is not algorithmically regular; official day counts per month vary; a table of official data is the only reliable approach | 2026-10-12 |

---

## Known Issues and Risks

| ID | Issue | Status | Notes |
|----|-------|--------|-------|
| KI-01 | Nepali STT quality | Open | Google Cloud STT is best available option; fallback to text-only mode documented in voice design |
| KI-02 | RAGAS evaluation requires real LLM API calls | Open | Not run in CI; must be run manually; documented in P13-T2 |
| KI-03 | Romanized Nepali detection may have false positives on short messages | Open | Will tune keyword list during P7-T2 |
| KI-04 | pgvector HNSW index rebuild required at > 100K chunks | Future | Documented; re-index script to be added in Phase 13 |

---

## Run Commands (Quick Reference)

```bash
# Start all services (dev)
docker-compose up -d

# Run DB migrations
cd backend && alembic upgrade head

# Seed demo data
cd backend && python scripts/seed_db.py

# Start API server (dev, hot reload)
cd backend && uvicorn app.main:app --reload --port 8000

# Start frontend (dev)
cd frontend && npm run dev

# Run all tests
cd backend && pytest

# Run with coverage
cd backend && pytest --cov=app --cov-report=html

# Lint
cd backend && ruff check . && ruff format --check .

# Type check
cd backend && mypy --strict app/

# Run full CI check
make ci   # runs lint + typecheck + test
```

---

## Changelog

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2026-10-12 | Kiro | Initial documentation phase complete: prd.md, architecture.md, rules.md, design.md, tasks.md, memory.md, steering files |
| 1.0.1 | 2026-10-12 | Kiro | P0-T1 complete: full project scaffold — docker-compose, pyproject.toml, alembic.ini+env.py, app/main.py, app/config.py, app/db/base.py, Dockerfiles, .env.example, .gitignore, Makefile, README.md, all __init__.py files, full directory tree |
| 1.0.2 | 2026-10-12 | Kiro | P0-T2 complete: venv created, all packages installed (fastapi 0.115.4, sqlalchemy 2.0.36, pydantic 2.8.2, langgraph, langchain, ruff, mypy, pytest 8.3.3 etc), ruff check passes, pytest collects without errors, config.py imports and loads correctly. Note: sentence-transformers/torch install pending (large download — not blocking). Decision recorded: Python 3.13.2 is used (machine default, not 3.12) — no functional difference for our code, recorded in memory. pyproject.toml build backend fixed (setuptools.build_meta). mypy overrides syntax fixed (individual [[tool.mypy.overrides]] blocks). asyncio_default_fixture_loop_scope set to function. |
| 1.0.3 | 2026-10-13 | Kiro | Phase 1 complete (P1-T1 through P1-T5): app/config.py, app/utils/logger.py (structlog, idempotent), app/middleware/logging.py, app/exceptions.py (full hierarchy), app/middleware/error_handler.py, app/middleware/rate_limit.py, app/dependencies.py, app/api/v1/health.py, app/main.py (full wiring). 25/25 tests pass. GET /health OK. Port changed to 5433 (5432 taken by twitter_postgres). |
| 1.0.4 | 2026-10-13 | Kiro | P2-T1 complete: 16 ORM models (user, guest, room, booking, seasonal_pricing, service, restaurant, document, conversation, handoff, notification) + __init__.py registry. All 16 models import cleanly, all 16 tables in Base.metadata. P2-T2 complete: Alembic migration generated and applied — alembic upgrade head created all 17 tables (16 + alembic_version), pgvector column vector(768) on document_chunks, HNSW index idx_chunks_embedding (m=16, ef=64). P2-T3 complete: seed_db.py — 4 room types, 39 rooms, 9 seasonal pricing (Dashain/Tihar/Chhath 2081+2082), 5 services, 8 tables, 2 users, 15 guests, 48 bookings (30 completed/13 confirmed/2 pending/3 cancelled), 15 table reservations. Idempotent. Decision: DocumentChunk.document_id FK was missing from model (caught at seed time), fixed and FK added to live DB and migration. app/auth/password.py created (bcrypt, passlib warning suppressed). |
| 1.0.5 | 2026-10-13 | Kiro | P2-T4 complete: 5 repositories (GuestRepository, RoomRepository, BookingRepository, DocumentRepository, HandoffRepository) with full async DB logic -- double-booking guard (SELECT FOR UPDATE), cancellation policy (>48h=100%, 24-48h=50%, <24h=0%), seasonal price calculation, document lifecycle management, handoff ticket CRUD. 25 integration tests all passing (function-scoped conn/session fixtures to avoid pytest-asyncio event_loop scope mismatch). Phase 2 complete. Total: 50/50 tests passing. |
| 1.0.6 | 2026-10-13 | Kiro | Phase 3 complete (P3-T1/T2/T3): app/auth/password.py (bcrypt, passlib warning suppressed), app/auth/jwt.py (create_access/refresh_token, decode, revoke, typed with Settings), app/auth/schemas.py (LoginRequest with custom email validator -- EmailStr rejected .local TLD), app/api/v1/auth.py (login/refresh/logout endpoints, 204 Response class fix), app/dependencies.py (get_current_user, require_role factory), app/api/v1/router.py (auth router wired). 27 new tests (unit + integration). Key decisions: EmailStr replaced with custom validator to allow .local dev domains; auth integration tests use DB session mocking (dependency_overrides) to avoid asyncpg event-loop-reuse error on Windows Python 3.13; WindowsSelectorEventLoopPolicy set in conftest.py; RATE_LIMIT_PER_MINUTE=10000 in test env. Total: 77/77 tests passing. |
| 1.0.7 | 2026-10-13 | Kiro | P4-T1 complete: 12 KB documents (8 EN + 4 NE Devanagari) -- hotel_policies, room_descriptions, restaurant_menu (20+ items with NPR prices), nearby_attractions, transfer_info, festival_packages, payment_methods, faq (10+ Q&A each language). P4-T2 complete: PDFLoader (PyMuPDF, per-page RawChunks), MarkdownLoader (per-section via heading regex), DevanagariAwareSplitter (danda/paragraph/sentence/newline/space priority chain, overlap, min_chunk_size, ClassVar fix). 10/10 splitter unit tests passing. Total: 87/87 tests passing. |
| 1.1.0 | 2026-10-16 | Qoder | Full environment verification + animation layer. See "Verification status": 161/161 tests, smoke 18/18, browser E2E (chat/booking/handoff/admin) on Docker mock-provider stack. Fixes: alembic+config env loading, booking/handoff list counts (Cartesian count), dev-mode streaming loss (impure StrictMode updaters in useChatSocket), WS half-open watchdog, CORS for :3100, JWT tamper test determinism. Added CSS animation layer (globals.css) across landing, chat and admin with prefers-reduced-motion guard. |
