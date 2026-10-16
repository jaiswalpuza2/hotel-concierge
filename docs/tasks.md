> **STATUS (2026-10-15):** Phases 0-13 are implemented. Per-task checkboxes below were not all ticked
> individually; see `docs/memory.md` "Completion summary" for the authoritative status and for what has and
> has not been verified.

# Implementation Task Plan
## Autonomous Multi-Agent Local Business Concierge
### Demo Instance: Himalayan Heritage Hotel

**Version:** 1.0.0  
**Date:** 2026-10-12  
**Status:** Phase 0 – Not Started

---

## How to Read This File

Each task has:
- A checkbox `[ ]` (ticked `[x]` when complete)
- An ID (e.g. `P0-T1`)
- A short title
- **Acceptance Criteria** – the specific, verifiable conditions that must be true before the task is considered done
- **Verification command** – exact terminal command(s) to confirm the task works

---

## Phase 0: Scaffolding and Environment

### P0-T1: Repository and project scaffold
- [x] **P0-T1** – Initialize repo structure, pyproject.toml, .env.example, docker-compose.yml, Makefile

**Acceptance Criteria:**
- `docker-compose.yml` defines services: `postgres` (PostgreSQL 16 + pgvector), `api` (FastAPI), `frontend` (Next.js)
- `pyproject.toml` lists all backend dependencies at pinned versions with `[project]`, `[tool.ruff]`, and `[tool.mypy]` sections
- `.env.example` contains every environment variable referenced in the codebase with descriptive comments
- `Makefile` has targets: `dev`, `test`, `migrate`, `seed`, `lint`, `typecheck`
- `README.md` has quick-start instructions
- Running `docker-compose up postgres` starts a healthy Postgres + pgvector container

**Verification:**
```bash
docker-compose up -d postgres
docker-compose exec postgres psql -U postgres -c "SELECT extversion FROM pg_extension WHERE extname='vector';"
```

### P0-T2: Backend Python environment and linting config
- [x] **P0-T2** – Configure ruff, mypy strict, pytest, structlog; create `app/` package skeleton

**Acceptance Criteria:**
- `ruff check .` exits 0 on the skeleton (no lint errors)
- `mypy --strict app/` exits 0 on the skeleton
- `pytest --collect-only` finds the `tests/` directory without import errors
- `app/main.py` exists and creates a FastAPI app instance
- `app/config.py` uses Pydantic Settings and reads from `.env`

**Verification:**
```bash
cd backend && ruff check . && mypy --strict app/ && pytest --collect-only
```

---

## Phase 1: FastAPI Core, Config, Logging, Middleware

### P1-T1: Pydantic Settings and configuration
- [x] **P1-T1** – Complete `app/config.py` with all settings, `.env.example` values

**Acceptance Criteria:**
- `Settings` class covers: DB_URL, JWT settings, LLM provider/model/key, embedding model, RAG thresholds, SMS/email/handoff providers, log level, CORS origins
- `get_settings()` is a cached dependency function
- `.env.example` is complete and all keys are documented

**Verification:**
```bash
cd backend && python -c "from app.config import get_settings; s = get_settings(); print(s.model_dump())"
```

### P1-T2: Structured logging middleware
- [x] **P1-T2** – Implement `app/middleware/logging.py` with request ID injection and JSON structlog output

**Acceptance Criteria:**
- Every request logs: `method`, `path`, `status_code`, `duration_ms`, `request_id` (UUID per request)
- Log output is valid JSON when `LOG_FORMAT=json`
- Request ID is injected into the response header `X-Request-ID`
- `structlog` is configured globally in `app/main.py`

**Verification:**
```bash
curl -s http://localhost:8000/health | jq .
# Check server log output is JSON with request_id field
```

### P1-T3: Global error handling middleware and custom exceptions
- [x] **P1-T3** – Implement `app/exceptions.py` and `app/middleware/error_handler.py`

**Acceptance Criteria:**
- `AppError` hierarchy: `ValidationError (400)`, `NotFoundError (404)`, `ConflictError (409)`, `AuthError (401)`, `ToolError (500)`, `IngestionError (500)`, `ProviderError (502)`
- Every `AppError` subclass maps to the correct HTTP status
- Stack traces are NOT included in the response body
- Error responses always have shape: `{"error": {"code": "...", "message": "...", "details": {...}}}`
- Unhandled exceptions return `500` with a generic message and log the full traceback internally

**Verification:**
```bash
pytest tests/unit/test_error_handling.py -v
```

### P1-T4: Rate limiting middleware
- [x] **P1-T4** – Implement `app/middleware/rate_limit.py` (60 req/min per IP, sliding window)

**Acceptance Criteria:**
- Requests beyond 60/min from the same IP get `429 Too Many Requests`
- Rate limit headers `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` are present on every response
- In-memory sliding window implementation (no Redis required in Phase 1)

**Verification:**
```bash
pytest tests/unit/test_rate_limit.py -v
```

### P1-T5: Health check endpoint
- [x] **P1-T5** – Implement `GET /health` with DB ping

**Acceptance Criteria:**
- Returns `{"status": "ok", "db": "ok", "version": "1.0.0"}` when DB is up
- Returns `{"status": "degraded", "db": "degraded"}` with HTTP 503 when DB is unreachable
- CORS headers are present (configured in `main.py`)

**Verification:**
```bash
curl http://localhost:8000/health
```

---

## Phase 2: Database, Alembic, Hotel Seed Data

### P2-T1: SQLAlchemy async setup and all ORM models
- [x] **P2-T1** – Implement `app/db/base.py` and all models in `app/db/models/`

**Acceptance Criteria:**
- `AsyncEngine` and `async_session_factory` created in `app/db/base.py` using `asyncpg`
- All 16 tables defined as SQLAlchemy 2.0 ORM models with correct types, FK relationships, and constraints
- `pgvector` `Vector` type used for `document_chunks.embedding`
- All models importable without errors

**Verification:**
```bash
cd backend && python -c "from app.db.models import guest, room, booking, document; print('OK')"
```

### P2-T2: Alembic migrations
- [x] **P2-T2** – Create Alembic initial migration covering all tables; configure async env

**Acceptance Criteria:**
- `alembic upgrade head` creates all 16 tables in the test DB without errors
- `alembic downgrade -1` drops them cleanly
- The migration file has the correct HNSW index creation for `document_chunks.embedding`
- `alembic current` shows the latest revision

**Verification:**
```bash
cd backend && alembic upgrade head && alembic current
```

### P2-T3: Hotel seed data script
- [x] **P2-T3** – Implement `scripts/seed_db.py` with all tables populated

**Acceptance Criteria:**
- 4 room types (Standard, Deluxe, Family Suite, Conference Hall) with realistic NPR prices
- 40 rooms distributed across types and floors
- At least 10 guests with a mix of en/ne preferred language
- At least 60 bookings across past 6 months and future 3 months
- At least 5 seasonal pricing entries covering Dashain, Tihar, Chhath 2081/2082 BS
- At least 8 restaurant tables, 15 table reservations
- At least 5 services (airport pickup, bus-park pickup, laundry, Koshi Tappu tour, Dharan tour)
- All phone numbers are valid Nepal format (98xxxxxxxx or 97xxxxxxxx)
- Script is idempotent (safe to run twice)

**Verification:**
```bash
cd backend && python scripts/seed_db.py
# Then:
docker-compose exec postgres psql -U postgres -d hoteldb -c "SELECT COUNT(*) FROM bookings;"
# Expected: ≥ 60
```

### P2-T4: Repository layer
- [x] **P2-T4** – Implement all repositories in `app/db/repositories/`

**Acceptance Criteria:**
- `BookingRepository`: `create_booking` (with `SELECT FOR UPDATE`), `get_by_id`, `get_by_guest_phone`, `cancel`, `list_all`
- `RoomRepository`: `find_available_rooms`, `get_price_with_seasonal`
- `GuestRepository`: `get_or_create_by_phone`, `get_by_id`
- `DocumentRepository`: `create`, `update_status`, `list_all`, `delete_with_chunks`
- `HandoffRepository`: `create_ticket`, `get_open_tickets`, `reply_and_resolve`
- All methods are `async def`, all use parameterized queries

**Verification:**
```bash
pytest tests/integration/test_repositories.py -v
```

---

## Phase 3: Authentication and Roles

### P3-T1: User model, password hashing, JWT
- [x] **P3-T1** – Implement `app/auth/password.py`, `app/auth/jwt.py`, seed admin user

**Acceptance Criteria:**
- `hash_password(plain: str) → str` uses bcrypt with 12 rounds
- `verify_password(plain: str, hashed: str) → bool` correct
- `create_access_token(user_id, role) → str` returns a valid JWT with correct expiry
- `decode_access_token(token) → TokenPayload` raises `AuthError` on expired or invalid token
- Seed script creates a default admin user `admin@hotel.local` / `Admin@2081`

**Verification:**
```bash
pytest tests/unit/test_auth.py -v
```

### P3-T2: Auth API endpoints
- [x] **P3-T2** – Implement `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`

**Acceptance Criteria:**
- `POST /auth/login` with valid credentials returns `{access_token, refresh_token, user}`
- `POST /auth/login` with invalid credentials returns `401` with `AuthError` body
- `POST /auth/refresh` with a valid refresh token returns a new access token
- `POST /auth/logout` invalidates the refresh token (store revoked JTI in Redis or DB)
- Access token is 15 minutes, refresh token is 7 days

**Verification:**
```bash
pytest tests/integration/test_auth.py -v
```

### P3-T3: Auth dependency and route protection
- [x] **P3-T3** – Implement `get_current_user` FastAPI dependency, apply to all admin routes

**Acceptance Criteria:**
- `get_current_user` extracts and validates JWT from `Authorization: Bearer` header
- Accessing any `/api/v1/` endpoint without a valid token returns `401`
- `require_role("admin")` dependency returns `403` for staff accessing admin-only routes
- Chat WebSocket endpoint uses a session token (not user JWT) and is publicly accessible

**Verification:**
```bash
pytest tests/integration/test_auth.py::test_protected_routes -v
```

---

## Phase 4: RAG Ingestion and Retrieval

### P4-T1: Knowledge base sample documents
- [x] **P4-T1** – Generate all 12 knowledge-base Markdown files (8 English, 4 Nepali)

**Acceptance Criteria:**
- Files exist in `knowledge_base/en/` and `knowledge_base/ne/`
- `hotel_policies.md` covers check-in (2 PM), check-out (11 AM), cancellation policy (full refund >48h, 50% 24-48h, no refund <24h), child policy (under 5 free), pet policy (not allowed), ID requirements (valid photo ID)
- `restaurant_menu.md` contains at least 20 items with NPR prices
- `faq.md` covers at least 10 common questions
- All Nepali files are in correct Devanagari script
- `scripts/generate_sample_docs.py` script generates these files programmatically (for reproducibility)

**Verification:**
```bash
python scripts/generate_sample_docs.py
ls knowledge_base/en/ knowledge_base/ne/
```

### P4-T2: Document loaders and Devanagari-aware splitter
- [x] **P4-T2** – Implement `app/rag/loaders.py` and `app/rag/splitter.py`

**Acceptance Criteria:**
- `PDFLoader.load(path) → list[RawChunk]` extracts text and page numbers using PyMuPDF
- `MarkdownLoader.load(path) → list[RawChunk]` extracts text and section headings
- `DevanagariAwareSplitter.split(chunks) → list[TextChunk]` splits on `।`, `?`, `!`, `\n\n`, and standard English sentence boundaries
- Chunk size: 512 tokens (approximated by character count × 0.25), overlap: 64 tokens
- Nepali text is not split mid-word

**Verification:**
```bash
pytest tests/unit/test_rag_splitter.py -v
```

### P4-T3: Embedding provider interface and multilingual embedding
- [ ] **P4-T3** – Implement `app/rag/embedder.py` with provider interface

**Acceptance Criteria:**
- `EmbeddingProvider` abstract base class with `async def embed(texts: list[str]) → list[list[float]]`
- `SentenceTransformerEmbedder` implementation using `paraphrase-multilingual-mpnet-base-v2` (768 dimensions)
- `OpenAIEmbedder` implementation using the configured OpenAI embedding model
- Model is selected by `EMBEDDING_PROVIDER` env var (`sentence_transformer` | `openai`)
- Both providers are tested to return vectors of the correct dimension

**Verification:**
```bash
pytest tests/unit/test_embedder.py -v
```

### P4-T4: pgvector store and ingestion pipeline
- [ ] **P4-T4** – Implement `app/rag/vector_store.py` and `app/rag/ingestion.py`

**Acceptance Criteria:**
- `VectorStore.insert_chunks(chunks_with_embeddings) → int` inserts all chunks and returns count
- `VectorStore.delete_by_document_id(doc_id)` removes all chunks and resets document status
- `ingest_document(document_id, file_path, mime_type)` orchestrates load → split → embed → store, updating `documents.status` at each step
- Status progresses: `queued → processing → indexed` (or `failed` with error message)
- The HNSW index is created on first insert if not already present

**Verification:**
```bash
pytest tests/integration/test_rag_retrieval.py::test_ingest -v
```

### P4-T5: Retriever and optional reranker
- [ ] **P4-T5** – Implement `app/rag/retriever.py`

**Acceptance Criteria:**
- `retrieve(query, top_k=5, threshold=0.6) → list[RetrievedChunk]` returns chunks sorted by score descending, filtered by threshold
- `RerankerProvider` abstract base class with `async def rerank(query, chunks) → list[RetrievedChunk]`
- `CrossEncoderReranker` implementation (optional, disabled by default)
- Retrieval query is embedded using the same model as ingestion

**Verification:**
```bash
pytest tests/integration/test_rag_retrieval.py -v
```

### P4-T6: Document management API endpoints
- [ ] **P4-T6** – Implement `POST /documents`, `GET /documents`, `DELETE /documents/{id}`

**Acceptance Criteria:**
- `POST /documents` validates file MIME type and size, creates DB record with `status=queued`, triggers background ingestion, returns `201` with document metadata
- `GET /documents` returns paginated list with current status
- `DELETE /documents/{id}` deletes DB record AND all vectors from pgvector
- Ingestion errors update `documents.error_message` and set `status=failed`

**Verification:**
```bash
pytest tests/integration/test_documents_api.py -v
```

---

## Phase 5: Tools and Mock DB Integration

### P5-T1: Tool input/output Pydantic schemas
- [ ] **P5-T1** – Implement `app/tools/schemas.py` with all 8 tool schemas

**Acceptance Criteria:**
- Every tool has a `<ToolName>Input` Pydantic model with field validators
- Every tool has a `<ToolName>Output` Pydantic model
- `ToolResult` generic wrapper: `{tool_name, success, data, error, duration_ms}`
- Phone number validator accepts Nepal format (98xxxxxxxx, 97xxxxxxxx, +977...)
- Date fields validate that `check_out > check_in`

**Verification:**
```bash
pytest tests/unit/test_tool_schemas.py -v
```

### P5-T2: Room availability and pricing tools
- [ ] **P5-T2** – Implement `app/tools/room_tools.py`

**Acceptance Criteria:**
- `check_room_availability`: queries `bookings` with non-overlapping date filter, returns available rooms by type with `SELECT FOR SHARE` to prevent phantom reads
- `get_room_price`: queries `seasonal_pricing` for the date range, applies multiplier to base price, returns itemised breakdown (base × nights × multiplier = total)
- Both functions are `async def` and use the injected DB session
- Seasonal multipliers for Dashain/Tihar/Chhath are correctly applied on overlapping date ranges

**Verification:**
```bash
pytest tests/unit/test_room_tools.py -v
pytest tests/integration/test_room_availability.py -v
```

### P5-T3: Booking tools (book, cancel, modify, status)
- [ ] **P5-T3** – Implement `app/tools/booking_tools.py`

**Acceptance Criteria:**
- `book_room`: `BEGIN TRANSACTION; SELECT room FOR UPDATE WHERE id=X; INSERT booking; COMMIT` — if room is taken, raises `ConflictError`
- `cancel_booking`: verifies `booking.guest.phone == input.phone`; applies cancellation policy (full refund >48h, 50% 24-48h, no refund <24h); updates status to `cancelled`
- `modify_booking`: checks availability for new dates with the same row-locking logic
- `get_booking_status`: returns full booking details including services
- All tools return `ToolResult` with `success=True/False`

**Verification:**
```bash
pytest tests/unit/test_booking_tools.py -v
pytest tests/integration/test_booking_flow.py -v
```

### P5-T4: Restaurant table reservation and service request tools
- [ ] **P5-T4** – Implement `app/tools/restaurant_tools.py` and `app/tools/service_tools.py`

**Acceptance Criteria:**
- `reserve_restaurant_table`: finds an available table for the given time and party size
- `request_service`: validates `booking_id` exists; creates `service_requests` row; returns service name and price
- Both are async and return `ToolResult`

**Verification:**
```bash
pytest tests/unit/test_service_tools.py -v
```

---

## Phase 6: LangGraph Multi-Agent Workflow

### P6-T1: Conversation state schema
- [ ] **P6-T1** – Implement `app/agents/state.py` with full `ConversationState` TypedDict

**Acceptance Criteria:**
- `ConversationState` is a `TypedDict` covering all fields from architecture.md §5
- All sub-schemas (`ToolCall`, `ToolResult`, `RetrievedChunk`, `BookingDraft`, `NotificationStatus`) are defined
- `IntentType` is a `Literal` with all 8 intent values
- mypy strict passes on the file

**Verification:**
```bash
cd backend && mypy --strict app/agents/state.py
```

### P6-T2: Postgres checkpointer
- [ ] **P6-T2** – Implement `app/agents/checkpointer.py` using LangGraph's Postgres checkpointer

**Acceptance Criteria:**
- `get_checkpointer()` returns an async Postgres checkpointer connected to the application DB
- Checkpointer creates the required LangGraph checkpoint tables on first use
- State is persisted between simulated process restarts (test: save state, reload, verify)

**Verification:**
```bash
pytest tests/integration/test_checkpointer.py -v
```

### P6-T3: All agent nodes
- [ ] **P6-T3** – Implement all 10 agent nodes in `app/agents/`

**Acceptance Criteria:**
- Each node is a pure `async def (state: ConversationState) → ConversationState`
- `route_intent`: calls LLM with supervisor prompt; parses JSON response; updates `state.intent`, `state.detected_language`, `state.confidence_score`
- `retrieve_chunks`: calls `retriever.retrieve()`; updates `state.retrieved_chunks`; increments `state.retry_count` on empty result
- `call_tools`: dispatches to the correct tool function based on `state.intent`; updates `state.tool_results`
- `draft_response`: calls LLM with grounded prompt (RAG or tool results); produces the final user-facing text; adds to `state.messages`
- `ask_confirmation`: formats `BookingDraft` and marks `state.awaiting_confirmation = True`
- `send_notifications`: dispatches Notification Agent async; does not block
- `evaluate_handoff`: checks all handoff trigger conditions; sets `state.escalation_reason`
- `create_handoff_ticket`: writes to DB; fires alert; sets `state.handoff_ticket_id`
- `await_human_reply`: no-op in normal flow; INTERRUPT fires here
- `forward_human_reply`: injects human reply into messages

**Verification:**
```bash
pytest tests/unit/test_agent_nodes.py -v
```

### P6-T4: LangGraph graph construction with all edges
- [ ] **P6-T4** – Implement `app/agents/graph.py` compiling the full graph

**Acceptance Criteria:**
- Graph has all nodes connected by the conditional edges defined in design.md §5.2
- `graph.compile(checkpointer=postgres_checkpointer)` succeeds
- `graph.get_graph().draw_mermaid()` produces a valid Mermaid diagram matching architecture.md §4
- Integration test: send a message → graph runs → response is produced → state is saved to checkpoint

**Verification:**
```bash
pytest tests/integration/test_graph_flow.py -v
```

---

## Phase 7: Bilingual Routing and Date Utility

### P7-T1: Bikram Sambat converter
- [ ] **P7-T1** – Implement `app/utils/bikram_sambat.py` with full calendar data 2070–2090 BS

**Acceptance Criteria:**
- `bs_to_gregorian(year, month, day)` correct for all test cases in golden test suite
- `gregorian_to_bs(date)` is the inverse of the above
- `parse_nepali_month_name(name)` handles all 12 months in Devanagari, Romanized, and common variants
- Raises `ValueError` for out-of-range dates
- 100% unit test coverage on this file

**Verification:**
```bash
pytest tests/unit/test_bikram_sambat.py -v --cov=app/utils/bikram_sambat --cov-report=term-missing
```

### P7-T2: Language detection utility
- [ ] **P7-T2** – Implement `app/utils/language_detection.py`

**Acceptance Criteria:**
- `detect_language(text: str) → Literal["en", "ne", "ne_roman"]`
- Devanagari text (contains Unicode range U+0900–U+097F) → `"ne"`
- English ASCII text → `"en"`
- Romanized Nepali heuristics (Nepali stopwords in Roman script: "ko", "ma", "cha", "garna", "bela", "kati", "parcha") → `"ne_roman"`
- Tested with all golden test conversation phrases

**Verification:**
```bash
pytest tests/unit/test_language_detection.py -v
```

### P7-T3: Date parsing in user messages (BS + Gregorian)
- [ ] **P7-T3** – Implement date extraction in agent pre-processing

**Acceptance Criteria:**
- If the user message contains a Nepali date (e.g., "5 Kartik", "५ कार्तिक", "Baisakh 10"), it is converted to Gregorian before being stored in `state`
- Date extraction uses the current year's BS calendar if only month+day are given
- If no year context, assume the nearest future date
- Extracted and converted dates logged at DEBUG level

**Verification:**
```bash
pytest tests/unit/test_date_parsing.py -v
```

### P7-T4: Golden conversation test suite
- [ ] **P7-T4** – Write and run all 5 golden conversation integration tests

**Acceptance Criteria:**
Each test sends the exact conversation from the PRD and asserts:
1. "Do you have a deluxe room for 2 people from 5 to 8 Kartik?" → intent=booking_intent, availability checked, price shown in NPR
2. "Dashain ko bela ma family suite kati parcha?" → lang=ne_roman, intent=faq or booking_intent, Dashain multiplier applied
3. "What time is check-out and can I get a late check-out?" → intent=faq, retrieval used, policy cited
4. "Mero booking cancel garna paryo" → asks for booking_id and phone before calling cancel_booking
5. "I want to complain about my room" → escalation_reason set, handoff_ticket created

**Verification:**
```bash
pytest tests/integration/test_golden_conversations.py -v
```

---

## Phase 8: Notification Agent

### P8-T1: Notification provider interfaces and mock implementations
- [ ] **P8-T1** – Implement `app/notifications/base.py`, `mock_sms.py`, `mock_email.py`

**Acceptance Criteria:**
- `SMSProvider` abstract class: `async def send_sms(phone: str, message: str) → NotificationResult`
- `EmailProvider` abstract class: `async def send_email(to: str, subject: str, body: str) → NotificationResult`
- `MockSMSProvider`: logs message to a file at `tmp/mock_sms.log`; returns `NotificationResult(success=True)`
- `MockEmailProvider`: logs to `tmp/mock_email.log`; returns `NotificationResult(success=True)`
- Provider selected by `SMS_PROVIDER=mock|sparrow` and `EMAIL_PROVIDER=mock|smtp` env vars

**Verification:**
```bash
pytest tests/unit/test_notification_providers.py -v
```

### P8-T2: Booking confirmation message templates (EN + NE)
- [ ] **P8-T2** – Implement message template rendering for confirmations

**Acceptance Criteria:**
SMS template (English, ≤160 chars):
```
Himalayan Heritage Hotel - Booking Confirmed!
ID: {booking_id}
Room: {room_type}, {check_in} to {check_out}
Total: रू {total_npr}
Check-in: 2:00 PM. Call: +977-25-XXXXXX
```
SMS template (Nepali):
```
हिमालयन हेरिटेज होटेल - बुकिङ पुष्टि भयो!
ID: {booking_id}
कोठा: {room_type}, {check_in} देखि {check_out} सम्म
जम्मा: रू {total_npr}
चेक-इन: दिउँसो २ बजे।
```
- Email includes all the same info plus hotel address and contact details
- Template rendering is tested for both languages

**Verification:**
```bash
pytest tests/unit/test_notification_templates.py -v
```

### P8-T3: Notification Agent node and retry logic
- [ ] **P8-T3** – Implement `app/agents/notification_agent.py` with retry and logging

**Acceptance Criteria:**
- Agent calls SMS and email providers concurrently (`asyncio.gather`)
- On first failure, retries once after 2 seconds
- Persistent failure writes to `notification_log` table with `status=failed` and does NOT raise an exception that blocks the user response
- `notification_log` row is written on success with `status=sent`

**Verification:**
```bash
pytest tests/integration/test_notification_agent.py -v
```

### P8-T4: Real SMS provider (Sparrow SMS)
- [ ] **P8-T4** – Implement `app/notifications/sparrow_sms.py`

**Acceptance Criteria:**
- `SparrowSMSProvider` implements `SMSProvider` and calls the Sparrow SMS REST API
- Auth token from `SMS_SPARROW_TOKEN` env var
- Sender name from `SMS_SPARROW_FROM` env var
- HTTP errors map to `ProviderError` with the status code and response body
- Timeout: 10 seconds

**Verification:**
```bash
# With a real Sparrow SMS token in .env:
pytest tests/integration/test_sparrow_sms.py -v -m "sparrow"
# (marked as skipped without the env var)
```

---

## Phase 9: Human Handoff with Telegram/Slack

### P9-T1: Handoff alert provider interfaces
- [ ] **P9-T1** – Implement `app/handoff/base.py`, `telegram_provider.py`, `slack_provider.py`

**Acceptance Criteria:**
- `HandoffAlertProvider` abstract class: `async def send_alert(ticket: HandoffTicket, conversation: list[Message]) → None`
- `TelegramProvider`: calls Telegram Bot API `sendMessage` to the configured chat ID; formats the alert as a clean HTML message
- `SlackProvider`: calls Slack Incoming Webhook URL; formats as a Slack block kit message
- Provider selected by `HANDOFF_PROVIDER=telegram|slack|mock` env var
- `MockHandoffProvider`: logs to `tmp/mock_handoff.log`

**Verification:**
```bash
pytest tests/unit/test_handoff_providers.py -v
```

### P9-T2: Handoff ticket API and admin reply flow
- [ ] **P9-T2** – Implement handoff API endpoints and WebSocket push for manager reply

**Acceptance Criteria:**
- `GET /api/v1/handoffs` returns open tickets first
- `POST /api/v1/handoffs/{id}/reply` stores `manager_reply`, changes status to `in_progress`, and **pushes the reply to the guest's active WebSocket connection within 5 seconds** using a session-keyed connection registry
- `PATCH /api/v1/handoffs/{id}/resolve` sets `status=resolved`, `resolved_at`, `resolved_by`
- The LangGraph checkpoint is updated with the human reply so the agent can resume

**Verification:**
```bash
pytest tests/integration/test_handoff.py -v
```

### P9-T3: LangGraph interrupt and resume
- [ ] **P9-T3** – Wire INTERRUPT node and resume logic in the graph

**Acceptance Criteria:**
- When `create_handoff_ticket` fires, the graph enters `await_human_reply` and saves the INTERRUPT checkpoint
- No automated messages are sent to the guest during INTERRUPT state
- When `POST /handoffs/{id}/reply` is called, it calls `graph.ainvoke(Command(resume=human_reply), config={"configurable": {"thread_id": session_id}})` to resume
- After resume, `forward_human_reply` node runs and sends the manager's reply to the guest WebSocket

**Verification:**
```bash
pytest tests/integration/test_handoff.py::test_interrupt_resume -v
```

---

## Phase 10: WebSocket and Voice

### P10-T1: Chat WebSocket endpoint
- [ ] **P10-T1** – Implement `app/api/ws/chat.py`

**Acceptance Criteria:**
- `/ws/chat/{session_id}` accepts connections with a query param `token` (session token, not JWT)
- Handles all message types from the WS protocol in design.md §3
- Streams LLM tokens to the client as `stream_delta` messages
- Maintains a connection registry (`session_id → WebSocket`) for handoff push
- Handles disconnection gracefully (saves checkpoint before closing)
- Rate limiting: max 1 concurrent connection per session_id

**Verification:**
```bash
pytest tests/integration/test_chat_websocket.py -v
```

### P10-T2: Voice WebSocket endpoint
- [ ] **P10-T2** – Implement `app/api/ws/voice.py`

**Acceptance Criteria:**
- `/ws/voice/{session_id}` accepts binary audio frames (16kHz, 16-bit PCM, mono)
- Streams audio to STT provider; on `end_of_speech` message, gets final transcript
- Passes transcript through the same LangGraph agent as text
- Streams TTS audio back to client in binary frames
- STT and TTS providers are swappable interfaces

**Verification:**
```bash
pytest tests/integration/test_voice_websocket.py -v
```

### P10-T3: STT and TTS provider interfaces
- [ ] **P10-T3** – Implement `app/voice/base.py`, `whisper_stt.py`, `google_tts.py`

**Acceptance Criteria:**
- `STTProvider` abstract: `async def transcribe(audio_bytes: bytes, language: str) → TranscriptResult`
- `TTSProvider` abstract: `async def synthesize(text: str, language: str) → bytes`
- `WhisperSTTProvider`: calls OpenAI Whisper API; returns transcript and detected language
- `GoogleTTSProvider`: calls Google Cloud TTS; uses `ne-NP` voice for Nepali, `en-US` for English
- Provider documentation includes Nepali support quality notes and fallback plan
- Providers selected by `STT_PROVIDER=whisper|google` and `TTS_PROVIDER=google` env vars

**Verification:**
```bash
pytest tests/unit/test_voice_providers.py -v
```

---

## Phase 11: Customer Chat Frontend

### P11-T1: Next.js project setup with TypeScript strict and Tailwind
- [ ] **P11-T1** – Initialize frontend with correct config

**Acceptance Criteria:**
- `tsconfig.json` has `"strict": true`
- Tailwind configured with custom colors (hotel brand palette: deep maroon, gold, cream)
- Devanagari font (Tiro Devanagari or Noto Sans Devanagari) loaded via `next/font`
- `npm run build` exits 0 with no TypeScript errors

**Verification:**
```bash
cd frontend && npm run build
```

### P11-T2: WebSocket hook and chat state management
- [ ] **P11-T2** – Implement `useWebSocket.ts` and `useChat.ts`

**Acceptance Criteria:**
- `useWebSocket` auto-reconnects with exponential backoff (max 5 retries)
- `useChat` maintains `messages: ChatMessage[]`, handles `stream_delta` by appending to the last message
- `useChat` handles `booking_confirm_prompt` by adding a special message type
- Language state is managed in `useChat` and sent with every message
- TypeScript: all types fully defined in `types/chat.ts`

**Verification:**
```bash
cd frontend && npm run typecheck
```

### P11-T3: ChatWindow, MessageList, MessageBubble, CitationBadge
- [ ] **P11-T3** – Implement core chat UI components

**Acceptance Criteria:**
- `MessageBubble` renders user messages right-aligned (blue), assistant messages left-aligned (white card)
- `MessageBubble` for `human_agent` role shows a yellow border and "Staff" label
- `CitationBadge` renders as a small pill `[Hotel Policies, p.2]`; on click shows full chunk text in a tooltip
- Streaming messages show a blinking cursor while `stream_end` has not yet been received
- All components are keyboard-navigable and meet WCAG 2.1 AA contrast

**Verification:**
```bash
cd frontend && npm run build && npm run lint
```

### P11-T4: InputBar, VoiceCapture, language toggle
- [ ] **P11-T4** – Implement input controls

**Acceptance Criteria:**
- `InputBar` sends message on Enter (without Shift), new line on Shift+Enter
- `MicButton` activates `MediaRecorder`; shows pulsing red indicator while recording; stops on second click or silence timeout
- `VoiceCapture` streams PCM audio chunks over the voice WebSocket
- Language toggle switches between `EN` and `नेपाली`; updates `useChat` state
- `HumanHandoffBanner` appears when `ChatWindow` receives a `handoff_started` message

**Verification:**
```bash
cd frontend && npm run build
# Manual browser test: open chat, speak, verify audio streams and response plays
```

---

## Phase 12: Admin Dashboard

### P12-T1: Admin login page and auth hook
- [ ] **P12-T1** – Implement JWT login, token storage, and `useAuth` hook

**Acceptance Criteria:**
- Login page at `/admin/login` with email + password form
- On success, stores `access_token` in memory and `refresh_token` in HTTP-only cookie
- `useAuth` hook exposes `{user, isAuthenticated, login, logout, refreshToken}`
- Auto-refresh: if access token is within 60s of expiry, refresh silently
- Unauthenticated access to any `/admin/*` page redirects to `/admin/login`

**Verification:**
```bash
cd frontend && npm run build
# Manual: login, verify token stored, try accessing /admin/documents
```

### P12-T2: Document management page
- [ ] **P12-T2** – Implement document upload and status tracking

**Acceptance Criteria:**
- Drag-and-drop upload with progress bar (uses `XMLHttpRequest` for upload progress events)
- After upload, document appears in list with status `queued`
- Status auto-refreshes every 3 seconds until `indexed` or `failed`
- `failed` status shows error message in red
- Delete button with confirmation dialog removes document from list

**Verification:**
```bash
cd frontend && npm run build
# Manual: upload a PDF, watch status change to indexed
```

### P12-T3: Handoff inbox
- [ ] **P12-T3** – Implement handoff ticket list and reply interface

**Acceptance Criteria:**
- Open tickets at the top, resolved at the bottom
- Each ticket card shows: trigger reason badge, time elapsed, guest language flag, conversation summary
- Inline reply textarea and Submit button
- After reply, ticket status changes to `in_progress` and the reply is shown in the card
- Resolve button moves ticket to resolved section

**Verification:**
```bash
cd frontend && npm run build
```

### P12-T4: Bookings and conversations pages
- [ ] **P12-T4** – Implement bookings list and conversation viewer

**Acceptance Criteria:**
- Bookings page has filters: date range, status, room type
- Booking table shows: booking ID, guest name (partially redacted phone), room, dates, status, total NPR
- Conversations page lists sessions with message count and detected language
- Clicking a conversation opens `ConversationViewer` showing full message history with intent labels and citation count

**Verification:**
```bash
cd frontend && npm run build
```

---

## Phase 13: Testing, Evaluation, Docker, Hardening

### P13-T1: Full pytest suite passing
- [ ] **P13-T1** – All unit and integration tests pass with ≥80% coverage on core modules

**Acceptance Criteria:**
- `pytest --cov=app/tools --cov=app/agents --cov=app/rag --cov=app/utils --cov-fail-under=80` exits 0
- No test is marked `xfail` without a documented reason
- All integration tests use the test DB (not production)

**Verification:**
```bash
cd backend && pytest --cov=app --cov-report=term-missing
```

### P13-T2: RAGAS golden Q&A evaluation
- [ ] **P13-T2** – Run RAG evaluation on the golden Q&A set

**Acceptance Criteria:**
- `eval/golden_qa_en.json` has ≥20 Q&A pairs
- `eval/golden_qa_ne.json` has ≥20 Q&A pairs covering Nepali-language queries
- `python eval/run_eval.py` outputs RAGAS faithfulness ≥ 0.85 and answer relevance ≥ 0.80 on the English set
- Nepali set results documented (target: ≥ 0.75 faithfulness)

**Verification:**
```bash
cd backend && python tests/eval/run_eval.py
```

### P13-T3: Docker production build
- [ ] **P13-T3** – Production-ready Docker images for both backend and frontend

**Acceptance Criteria:**
- `backend/Dockerfile` uses multi-stage build; final image < 1.2 GB; runs as non-root user
- `frontend/Dockerfile` uses multi-stage build (build → node:alpine serve); final image < 300 MB
- `docker-compose.yml` has a `production` profile and a `dev` profile
- All secrets passed via environment variables; no secrets baked into images
- `docker-compose up` (dev) starts all services and health checks pass within 60s

**Verification:**
```bash
docker-compose build
docker-compose up -d
curl http://localhost:8000/health
```

### P13-T4: Load test for double-booking guard
- [ ] **P13-T4** – Concurrent booking test confirms no double-booking

**Acceptance Criteria:**
- Test sends 10 concurrent `book_room` requests for the same room and same dates
- Exactly 1 succeeds; 9 receive `409 Conflict` with `ConflictError` body
- No data corruption in the `bookings` table

**Verification:**
```bash
pytest tests/integration/test_concurrent_booking.py -v
```

### P13-T5: Security hardening checklist
- [ ] **P13-T5** – Verify all security requirements

**Acceptance Criteria:**
- `ruff check --select S .` (bandit rules) exits 0 (no security issues)
- `pip-audit` (or `safety check`) shows no critical vulnerabilities in dependencies
- `.env` is in `.gitignore`; `git log --all -- .env` shows no commits containing `.env`
- All API endpoints tested for authentication: unauthenticated requests return `401`, not `500`
- File upload rejects non-PDF/Markdown files and files > 20 MB

**Verification:**
```bash
cd backend && ruff check --select S . && pip-audit
```
