---
inclusion: always
---

# Coding Standards (Kiro Session Rules)
## Autonomous Multi-Agent Local Business Concierge

This file is auto-included in every Kiro session. These rules are non-negotiable.

## The Golden Rules

1. **No placeholders.** Every file produced is fully implemented. No `# TODO`, no `pass`, no stub functions. If a file is not ready to be fully implemented, it is not written yet.

2. **One task at a time.** Implement exactly one task from `docs/tasks.md` per turn. Do not skip ahead or bundle tasks.

3. **Read before writing.** Before writing any code, read the relevant existing files to understand context and avoid conflicts.

4. **Update `docs/tasks.md` and `docs/memory.md` after every task.** Tick the checkbox. Record what was done, decisions made, and known issues.

5. **Verify after every task.** Run `ruff`, `mypy --strict`, and the relevant `pytest` tests. Fix all errors before reporting the task as done.

6. **Stop and ask.** After completing a task, summarise what was done, show test output, and ask the user to confirm before moving to the next task.

## Python Rules

- Python 3.12 only. All files start with `from __future__ import annotations`.
- Every function, method, and attribute has a complete type annotation. No `Any` without a comment.
- All async — use `async def` for all route handlers, all DB operations, all external calls.
- Never call blocking I/O from async context. Use `asyncio.to_thread` or `aiofiles`.
- Custom exceptions only — never raise bare `Exception`. Use the `AppError` hierarchy.
- All SQL via SQLAlchemy ORM or parameterised `text()`. No f-string SQL ever.
- All secrets via environment variables. Never hardcoded.
- Structlog for all logging. Every log line includes `request_id` and `session_id` where available. Never log PII.

## Naming Conventions

- Modules: `snake_case`
- Classes: `PascalCase`
- Functions / methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Pydantic schemas: `PascalCase` + noun (e.g. `BookingCreateRequest`, `BookingResponse`)
- FastAPI handlers: verb + noun (e.g. `create_booking`, `get_booking`)
- LangGraph nodes: `snake_case` verbs (e.g. `route_intent`, `retrieve_chunks`)

## Testing Rules

- Framework: pytest + pytest-asyncio (mode=auto)
- Every tool function: happy path + validation error + not-found/conflict
- Every agent node: at least one unit test with mocked LLM
- Integration tests use a real test DB; never mock the DB in integration tests
- Minimum 80% coverage on `app/tools/`, `app/agents/`, `app/rag/`, `app/utils/`

## Git Rules

- Commit format: `<type>(<scope>): <description>` (Conventional Commits)
- No direct commits to `main`
- No `--no-verify`
- `.env` always in `.gitignore`; never commit secrets

## Business-Type Abstraction Rule

All business-specific config (hotel name, room types, tool set, prompts, KB path) lives in configuration files or the DB. **Never hardcode "hotel" or "Himalayan Heritage" into reusable agent logic.** The agents, graph, and tools must work with any business type by swapping config.
