# Coding Standards and Project Rules
## Autonomous Multi-Agent Local Business Concierge

**Version:** 1.0.0  
**Date:** 2026-10-12  
**Applies to:** All contributors and all Kiro agent sessions

---

## 1. General Principles

1. **No placeholders.** Every file written must be fully implemented with all imports, type hints, logic, and docstrings. Strings like `# TODO`, `pass  # implement later`, or `raise NotImplementedError` are forbidden in committed code.
2. **One concern per file.** Each module has a single, clearly named responsibility. Shared utilities live in `utils/`; ORM models live in `db/models/`; they do not cross-import improperly.
3. **Explicit over implicit.** No magic strings, no hardcoded credentials, no raw numbers where a named constant or config value belongs.
4. **Production quality at all times.** There is no "we'll harden it later" phase. Auth, validation, error handling, and logging are built in from the first line of each module.

---

## 2. Python Standards

### 2.1 Version and Tooling
- Python **3.12** only. No syntax or features from earlier versions.
- Formatter: **ruff format** (replaces black). Line length: 100.
- Linter: **ruff** with the following rule sets enabled: `E, W, F, I, N, UP, B, C4, SIM, RUF`.
- Type checker: **mypy** in strict mode (`--strict`). All files must pass with zero errors.
- Dependency management: **uv** or **pip-compile**. All deps pinned to exact versions in `pyproject.toml`.

### 2.2 Naming
| Construct | Convention | Example |
|-----------|-----------|---------|
| Modules | `snake_case` | `booking_tools.py` |
| Classes | `PascalCase` | `BookingRepository` |
| Functions / methods | `snake_case` | `check_room_availability` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_RETRY_COUNT = 2` |
| Type aliases | `PascalCase` | `BookingId = UUID` |
| Private attributes | single leading underscore | `_db_session` |
| Pydantic models (schemas) | `PascalCase` + noun | `BookingCreateRequest`, `BookingResponse` |
| FastAPI route handlers | verb + noun | `create_booking`, `get_booking` |
| LangGraph nodes | `snake_case` verbs | `route_intent`, `retrieve_chunks`, `call_tools` |

### 2.3 Type Hints
- Every function, method, and class attribute MUST have a complete type annotation.
- Use `from __future__ import annotations` in all files for forward references.
- Use `typing.Literal` for constrained string choices.
- Use `typing.TypedDict` for LangGraph state schemas.
- Never use `Any` unless interfacing with a truly untyped external library, and document why.
- Pydantic v2 models MUST use `model_config = ConfigDict(...)` syntax; do not use the inner `class Config` pattern.

### 2.4 Async Rules
- All database operations MUST use `async/await` with SQLAlchemy 2.0 async sessions.
- All HTTP calls to external providers (LLM, SMS, Email, STT, TTS) MUST use `httpx.AsyncClient`.
- Never call a blocking function (`requests`, `time.sleep`, `open()` for large files) from an async context. Use `asyncio.to_thread` or `aiofiles` if blocking I/O is unavoidable.
- FastAPI route handlers MUST be `async def`.
- WebSocket handlers MUST use `async for` / `await ws.send_*`.
- Background tasks (FastAPI `BackgroundTasks`) MUST be async coroutines.

### 2.5 Error Handling
- Define a custom exception hierarchy rooted at `AppError(Exception)` in `app/exceptions.py`.
- Sub-classes: `ValidationError`, `NotFoundError`, `ConflictError`, `AuthError`, `ToolError`, `IngestionError`, `ProviderError`.
- All exceptions MUST carry: `message: str`, `code: str` (machine-readable slug), `details: dict | None`.
- The global error handler middleware converts every `AppError` subclass to its appropriate HTTP status code and JSON body. It never leaks stack traces to clients.
- Tool functions MUST return a `ToolResult` with `success=False` and a structured `error` on failure; they MUST NOT raise exceptions into the agent loop directly (the agent loop catches and retries).
- Use `try/except` narrowly — catch only the specific exception types you expect.

### 2.6 Logging
- Use **structlog** configured for JSON output.
- Every log entry MUST include: `timestamp`, `level`, `request_id`, `session_id` (when in a chat context), `module`, `function`.
- Never log raw PII (phone numbers, email addresses, full names). Redact with `***` or log only the first 4 characters.
- Log every tool call entry and exit: `tool_call.start` with input args (PII redacted), `tool_call.success` or `tool_call.error` with duration_ms.
- Log every LLM call: `llm.request` with model name and prompt token count, `llm.response` with completion token count and duration_ms.
- Log every agent node entry: `agent.node.enter` with node name and current intent.
- Log level per environment: `DEBUG` in development, `INFO` in staging, `WARNING` in production (overridable via `LOG_LEVEL` env var).

### 2.7 Security
- All SQL executed through SQLAlchemy ORM or parameterized `text()` constructs. No f-string SQL.
- File upload handlers MUST validate MIME type (allowlist: `application/pdf`, `text/markdown`, `text/plain`) and file size (max `20_971_520` bytes = 20 MB).
- Passwords hashed with `bcrypt` (12 rounds minimum). Never stored in plaintext.
- JWT: use `python-jose` or `authlib`. Access token expiry: `ACCESS_TOKEN_EXPIRE_MINUTES` from config. Refresh token expiry: `REFRESH_TOKEN_EXPIRE_DAYS`. Algorithm: HS256. Secret: `JWT_SECRET_KEY` env var.
- Secrets loaded exclusively from environment variables via Pydantic Settings. Never hardcoded in source files or test fixtures.
- Rate limiting middleware applied to all public endpoints (chat, voice WebSocket handshake).

---

## 3. Database Standards

- Use **Alembic** for all schema changes. Never modify the DB schema by hand.
- Each migration file has a descriptive name: `2024_10_12_001_create_rooms_table.py`.
- All ORM models inherit from a common `Base` and define `__tablename__`, all columns with types, and all FK relationships explicitly.
- Use `UUID` primary keys for all entities except lookup/enum tables (e.g., `room_types.id` can be a short varchar slug).
- All timestamps MUST be `TIMESTAMP WITH TIME ZONE` stored in UTC.
- All monetary amounts stored as `INTEGER` (paise/paisa, i.e., NPR * 100) or as `INTEGER` NPR if sub-rupee precision is not needed (hotel use case: whole NPR is fine).
- Add DB-level `CHECK` constraints for critical business rules (e.g., `check_out > check_in`, `guests_count > 0`).
- The `document_chunks.embedding` column uses `pgvector` type `vector(768)` (or match the embedding model's dimension, set via `EMBEDDING_DIMENSIONS` env var).
- Create an HNSW index on `document_chunks.embedding` with `m=16, ef_construction=64` as the default.

---

## 4. API Standards

- All REST endpoints live under `/api/v1/`.
- Use Pydantic v2 models for all request bodies and response models; enable `response_model_exclude_unset=True` on FastAPI routes.
- HTTP status codes must follow REST semantics: `200 OK`, `201 Created`, `204 No Content`, `400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`, `409 Conflict`, `422 Unprocessable Entity`, `500 Internal Server Error`.
- Paginated list endpoints use `?page=1&page_size=20` query params and return `{items: [...], total: N, page: N, page_size: N}`.
- All API responses are JSON. Never return plain text or HTML from an API endpoint.
- WebSocket messages use a typed JSON protocol defined in `ws-protocol.ts` (frontend) and mirrored as TypedDicts in `app/api/ws/`.

---

## 5. LangGraph / Agent Standards

- LangGraph state is always a `TypedDict` defined in `agents/state.py`. No ad-hoc dict keys.
- Every agent node is a pure `async def` function: `async def node_name(state: ConversationState) -> ConversationState`.
- Nodes MUST NOT call the DB or external providers directly. They call repository functions or provider interfaces, which are injected or imported from the appropriate modules.
- Conditional edges MUST be named functions, not lambdas, so the graph is inspectable.
- The graph is compiled once at startup and reused. Use the Postgres checkpointer for all state persistence.
- Agent retries: `MAX_TOOL_RETRIES = 2` and `MAX_RETRIEVAL_RETRIES = 2` are constants in `config.py`.
- Interrupts: only the `GuardrailAgent` node may set `interrupt_before` on the graph. Interrupt state is always saved to the Postgres checkpointer before the interrupt fires.

---

## 6. Testing Standards

- Framework: **pytest** + **pytest-asyncio** (mode=`auto`).
- Every tool function has at least one unit test covering: (a) happy path, (b) validation error, (c) not-found or conflict case.
- Every agent node has at least one unit test with a mocked LLM response.
- Integration tests use a real test PostgreSQL database spun up by the pytest session fixture. No mocking of the DB in integration tests.
- Test fixtures must not leave data in the DB after the test (use transactions rolled back in teardown).
- The `eval/` suite runs the RAGAS golden Q&A set. It is NOT run in CI by default (it requires real LLM API calls) but is documented and runnable manually.
- Minimum test coverage: 80% for `app/tools/`, `app/agents/`, `app/rag/`, `app/utils/`. Enforced with `pytest-cov --fail-under=80`.
- Test file naming: `test_<module_name>.py`. Test function naming: `test_<thing_being_tested>_<scenario>`.

---

## 7. Git and Commit Standards

- Commit message format: `<type>(<scope>): <short description>` (Conventional Commits).
  - Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci`
  - Examples: `feat(booking): add double-booking guard with row locking`, `fix(bs-converter): handle Chaitra leap day correctly`
- Branch names: `feat/<short-slug>`, `fix/<short-slug>`, `chore/<short-slug>`.
- Every branch must pass `ruff`, `mypy --strict`, and `pytest` before merging.
- No direct commits to `main`. All changes via pull requests.
- Secrets (`.env`, credentials) MUST be in `.gitignore` and MUST never be committed.

---

## 8. Kiro Agent Rules (how Kiro must work in this project)

These rules apply in every Kiro session on this codebase:

1. **One task at a time.** Kiro implements exactly one task from `tasks.md` per turn. Kiro does not skip ahead.
2. **Read before writing.** Before writing any code, Kiro reads the relevant existing files to understand the current structure and avoid conflicts.
3. **No placeholders.** Every file Kiro produces is fully implemented. No `# TODO`, no `pass`, no stub that works "in theory."
4. **Update `tasks.md` and `memory.md` after every task.** The task checkbox is ticked, the memory file is updated with: current phase/task, what was done, any decisions made, and any known issues.
5. **Run verification after every task.** Kiro runs `ruff`, `mypy`, and the relevant `pytest` tests for the module just written. If they fail, Kiro fixes the errors before reporting the task as done.
6. **Stop and ask before continuing.** After completing a task, Kiro summarises what was done, shows the test output, and asks the user to confirm before moving to the next task.
7. **Record decisions.** Any architectural decision (even small ones) is recorded in `memory.md` under "Decisions."
8. **Ask one clear question.** If a requirement is ambiguous, Kiro asks one clear, specific question. Kiro does not make assumptions for ambiguous requirements.
9. **Flag impractical requirements.** If a requirement is technically impractical or would introduce unacceptable risk, Kiro says so clearly, proposes the best alternative, and records the decision.
10. **Explain concepts.** For each task, Kiro briefly explains what the code does in plain language accessible to a beginner, without oversimplifying the architecture.
11. **Never install unverified packages.** All packages must be from `pyproject.toml` or `package.json` as defined in the tech stack. Kiro does not add new dependencies without explaining why and getting approval.
12. **Keep the business-type abstraction.** All business-specific config (hotel name, room types, tool set, prompts, KB path) lives in configuration files or the DB. Kiro never hardcodes "hotel" into reusable agent logic.

---

## 9. Environment Variable Standards

- All env vars defined in `.env.example` with descriptive comments.
- Pydantic Settings in `config.py` reads them with `model_config = ConfigDict(env_file=".env")`.
- All secrets use `SecretStr` type in the Settings model so they are redacted in logs and repr.
- Env var naming: `UPPER_SNAKE_CASE`, prefixed by category: `DB_`, `JWT_`, `LLM_`, `SMS_`, `EMAIL_`, `TELEGRAM_`, `VOICE_`, `RAG_`.

---

## 10. Documentation Standards

- Every public function and class has a Google-style docstring with: summary line, Args, Returns, and Raises sections.
- Inline comments explain *why*, not *what* (the code should be readable enough to explain what).
- README.md at the repo root has: project overview, quick-start (clone, copy .env.example, docker-compose up, seed), and links to all docs/ files.
- Architecture decisions that affect future development are recorded in `memory.md` under "Decisions."
