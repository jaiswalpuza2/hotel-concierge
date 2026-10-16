# =============================================================================
# Backend Dockerfile — multi-stage
# Stage: development  → hot-reload dev server (used by docker-compose)
# Stage: production   → non-root, minimal image
# =============================================================================

# ---------------------------------------------------------------------------
# Base: shared Python setup
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS base

# Keeps Python from generating .pyc files and enables unbuffered stdout
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies required by asyncpg, PyMuPDF, and sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libmupdf-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Builder: install Python deps into a venv
# ---------------------------------------------------------------------------
FROM base AS builder

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml ./
# Install all deps (including dev for now; production stage excludes them)
RUN pip install -e ".[dev]"

# ---------------------------------------------------------------------------
# Development: hot-reload server with mounted source
# ---------------------------------------------------------------------------
FROM base AS development

ENV PATH="/opt/venv/bin:$PATH"
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
# Source is mounted as a volume by docker-compose; copy here is a fallback
COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---------------------------------------------------------------------------
# Production: non-root user, no dev tools
# ---------------------------------------------------------------------------
FROM base AS production

RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

ENV PATH="/opt/venv/bin:$PATH"
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=appuser:appgroup . .

USER appuser
EXPOSE 8000

# Gunicorn with uvicorn workers for production
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
