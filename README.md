# Himalayan Heritage Hotel — AI Concierge
### Autonomous Multi-Agent Local Business Concierge (English · नेपाली · Romanized Nepali)

An AI concierge for regional Nepali businesses (demo: a 40-room hotel in the Itahari/Dharan region). It
answers from the hotel's own documents (RAG, with citations), checks **live** availability and prices,
books and cancels rooms behind safety guards, sends SMS/email confirmations, and hands difficult
conversations to a human manager over Telegram or Slack, with the manager's reply appearing live in
the guest's chat. Guests can type or speak.

```
Guest (Next.js chat, text + voice)  ──WebSocket──►  FastAPI gateway
                                                      │
                                           LangGraph multi-agent workflow
   ingest → supervisor ─┬─ smalltalk
                        ├─ RAG:   retrieve ⇄ rewrite_query → rag_answer → guardrail ─┐
                        ├─ Tools: tool_agent ⇄ tool_exec (loop, retries, guards) ────┼→ compose → notify → finalize
                        ├─ handoff (ticket + Telegram/Slack alert)                   │
                        └─ human_relay (AI stays silent while a human is assigned)  ─┘
                                                      │
              PostgreSQL: bookings, rooms, guests, tickets, messages, pgvector chunks, LangGraph checkpoints
```

## What is in the box

| Capability | Where |
|---|---|
| Bilingual routing: English, Devanagari Nepali, Romanized Nepali ("kati parcha"), UI language toggle | `backend/app/utils/nepali_text.py`, `agents/graph_spec.py` (`ingest`), `agents/prompts.py`, `agents/messages.py` |
| Bikram Sambat ⇄ Gregorian dates ("5 to 8 Kartik") | `backend/app/utils/bikram_sambat.py` (**read the calendar note below**) |
| Multi-agent LangGraph workflow with loops, conditional edges, checkpointing | `backend/app/agents/` |
| RAG: PDF/Markdown → recursive splitting (Devanagari-aware) → multilingual embeddings → pgvector cosine search → citations | `backend/app/rag/` |
| 10 live tools (availability, quote, book, cancel, modify, status, restaurant table, services, hours, knowledge search) | `backend/app/tools/` |
| Booking safety: signed expiring price quotes, explicit-confirmation flag, row-locked double-booking guard, phone+reference verification | `tools/quotes.py`, `tools/hotel_tools.py`, `db/repositories/booking_repo.py` |
| Notification agent: SMS (Sparrow) + email (SMTP) with retries and a delivery log | `backend/app/notifications/` |
| Human handoff: triggers, tickets, Telegram/Slack alerts, manager replies pushed live, resolve → AI resumes | `backend/app/handoff/`, `api/v1/admin.py` |
| Voice: MediaRecorder streaming over WebSocket → Whisper (Nepali supported) → agent → TTS → Web Audio playback; browser speech fallback | `backend/app/voice/`, `api/ws/chat.py`, `frontend/src/hooks/` |
| Admin dashboard: document upload + live indexing status, handoff inbox, conversations, bookings | `frontend/src/app/admin/` |
| Auth: JWT access tokens in memory + HttpOnly refresh cookie (via Next.js route handlers) | `backend/app/auth/`, `frontend/src/app/api/auth/` |
| LLM providers (swap with one env var): OpenAI-compatible, Anthropic, Ollama, offline **mock** | `backend/app/llm/` |

## Quick start (Docker — recommended, also the easiest on Windows)

Prerequisites: Docker Desktop. Nothing else is required to try it.

```bash
cp .env.example .env            # Windows PowerShell: copy .env.example .env
#  The defaults run fully offline: LLM_PROVIDER=mock. Change JWT_SECRET_KEY before deploying.

docker compose up -d --build    # starts PostgreSQL+pgvector, the API (runs migrations), the frontend
docker compose exec api python scripts/seed_db.py        # demo hotel data + staff users (wipes data!)
docker compose exec api python scripts/ingest_kb.py      # index English + Nepali sample documents
#   (first run downloads the ~1 GB multilingual embedding model; for a 10-second try-out set
#    EMBEDDING_PROVIDER=hashing and RETRIEVAL_CONFIDENCE_THRESHOLD=0.25 in .env first)

docker compose exec api python scripts/smoke_test.py     # end-to-end self-check (see below)
```

Open:
- Guest chat: http://localhost:3000/chat
- Staff dashboard: http://localhost:3000/admin — `admin@hotel.local` / `Admin@2081` or `staff@hotel.local` / `Staff@2081` (**demo passwords: change them**)
- API docs: http://localhost:8000/docs

### Running without Docker (Windows PowerShell)

```powershell
docker compose up -d postgres                  # database only (port 5433 on the host)
cd backend
py -3.12 -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy ..\.env.example ..\.env                   # DB_URL already points to localhost:5433
alembic upgrade head
python scripts/seed_db.py
python run.py                                  # NOT plain `uvicorn`: run.py selects the Windows event loop
                                               # that psycopg (LangGraph's Postgres checkpointer) needs
# second terminal
python scripts/ingest_kb.py
cd ..\frontend ; npm install ; npm run dev     # http://localhost:3000
```
If you start the API with plain `uvicorn` on Windows the app still works, but conversation memory falls
back to RAM (you will see a `checkpointer.postgres_unavailable_using_memory` warning).

## Using a real LLM, voice, SMS, Telegram/Slack

Everything is switched in `.env` (see the comments there):

| Goal | Settings |
|---|---|
| Real AI | `LLM_PROVIDER=openai` + `LLM_API_KEY` + `LLM_MODEL`, or `anthropic` (e.g. `claude-haiku-5-5`), or `ollama` (local; pick a model with tool-calling support) |
| Voice input (server) | `STT_PROVIDER=whisper` + `OPENAI_WHISPER_API_KEY` (supports Nepali). Without it the mic button uses the browser's own speech recognition (`ne-NP` / `en-US`) |
| Spoken replies | `TTS_PROVIDER=openai` (clear English, Nepali is approximate) or `google` (`pip install -e ".[voice-google]"` + service-account credentials; has a Nepali voice) |
| SMS | `SMS_PROVIDER=sparrow`, `SMS_SPARROW_TOKEN`, `SMS_SPARROW_FROM` |
| Email | `EMAIL_PROVIDER=smtp` + `SMTP_*` |
| Manager alerts | `HANDOFF_PROVIDER=telegram` (+ `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) or `slack` (+ `SLACK_WEBHOOK_URL`) |

`LLM_PROVIDER=mock` is a rule-based demo brain (not AI) so you can exercise routing, tools, handoff,
voice and the UI for free. Judge answer quality only with a real model.

## Verify it works

```bash
cd backend
pytest tests/unit                      # pure-logic tests: calendar, language detection, routing,
                                       # agent workflow scenarios, templates, quotes, tool schemas
pytest tests/integration               # repositories + auth against a real PostgreSQL
python scripts/smoke_test.py           # drives the RUNNING stack: RAG + citations, availability with
                                       # Bikram Sambat dates, guarded booking, Romanized Nepali,
                                       # handoff → manager reply → resolve
```

## Production checklist (please read)

1. **Verify the Bikram Sambat table.** `bikram_sambat.py` supports BS 2080–2084. The New Year anchors are
   consistency-tested, but a day moved between two months of the same year would not be caught. Check each
   month length against the official panchang before relying on mid-year conversions, and extend the table
   from the same source. The agent always echoes dates in both calendars so a guest can correct a mistake.
2. **Festival pricing** (`seed_db.py`) uses approximate Dashain/Tihar/Chhath dates; they move every year.
3. **Secrets and passwords:** set a long random `JWT_SECRET_KEY` (the API refuses to start in
   `APP_ENV=production` with the default), change the seeded staff passwords, serve over HTTPS.
4. **Scale-out:** the live-push registry (`api/ws/manager.py`) is in-process. For several API workers,
   back `push` with Redis pub/sub (the interface is isolated for this).
5. **`seed_db.py` deletes all existing data**, including indexed documents. Run it only on a fresh database.
6. **Cost control:** rate limits are per IP (`middleware/rate_limit.py`); add per-session limits before public launch.
7. **Embedding model change** ⇒ re-index documents and keep `EMBEDDING_DIMENSIONS` equal to the vector column size (768).

## Other businesses

`BUSINESS_TYPE` selects a profile (`backend/app/business/profiles.py`). The hotel ships with the full tool set.
Hospital, agricultural co-op and retail profiles are knowledge-base-only today (answers from uploaded
documents + human handoff). To add live tools for one, write a `ToolExecutor` next to
`tools/hotel_tools.py` and select it in `agents/runtime.py`.

## Project documentation

`docs/` holds the PRD, architecture, design, rules, task plan and living `memory.md` (status, decisions,
changelog). The agent flow in code is declared in `backend/app/agents/graph_spec.py`.
