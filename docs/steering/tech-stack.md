---
inclusion: always
---

# Tech Stack and Version Pins
## Autonomous Multi-Agent Local Business Concierge

This file is auto-included in every Kiro session. All versions are pinned. Do not upgrade a dependency without recording the decision in `docs/memory.md`.

## Backend (Python)

| Package | Version | Purpose |
|---------|---------|---------|
| Python | 3.12 | Runtime |
| fastapi | 0.115.x | Web framework |
| uvicorn[standard] | 0.30.x | ASGI server |
| sqlalchemy[asyncio] | 2.0.x | ORM |
| asyncpg | 0.29.x | PostgreSQL async driver |
| alembic | 1.13.x | DB migrations |
| pgvector | 0.3.x | pgvector Python client |
| langgraph | 0.2.x | Multi-agent orchestration |
| langchain | 0.3.x | LLM abstraction |
| langchain-openai | 0.2.x | OpenAI LLM/embedding provider |
| pydantic | 2.8.x | Data validation |
| pydantic-settings | 2.5.x | Settings from env |
| structlog | 24.x | Structured logging |
| httpx | 0.27.x | Async HTTP client |
| python-jose[cryptography] | 3.3.x | JWT |
| bcrypt | 4.x | Password hashing |
| PyMuPDF | 1.24.x | PDF text extraction |
| sentence-transformers | 3.x | Multilingual embeddings |
| ruff | 0.6.x | Linter + formatter |
| mypy | 1.11.x | Type checker |
| pytest | 8.x | Test framework |
| pytest-asyncio | 0.24.x | Async test support |
| pytest-cov | 5.x | Coverage |
| pip-audit | latest | Dependency security scan |

## Database

| Component | Version |
|-----------|---------|
| PostgreSQL | 16 |
| pgvector extension | 0.7.x |

## Frontend (Node.js)

| Package | Version | Purpose |
|---------|---------|---------|
| Node.js | 20 LTS | Runtime |
| next | 14.x | App Router framework |
| react | 18.x | UI library |
| react-dom | 18.x | DOM renderer |
| typescript | 5.x | Type safety |
| tailwindcss | 3.x | Utility CSS |
| @types/react | 18.x | React types |
| eslint | 8.x | JS/TS linting |
| eslint-config-next | 14.x | Next.js ESLint config |

## Infrastructure

| Tool | Purpose |
|------|---------|
| Docker | Container runtime |
| docker-compose | Local orchestration |
| Nginx / Traefik | Reverse proxy (production) |
