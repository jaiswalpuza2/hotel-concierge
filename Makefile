# =============================================================================
# Makefile — Autonomous Multi-Agent Local Business Concierge
# =============================================================================
# Usage: make <target>
# All targets that run Python commands use the backend virtualenv.
# Set VENV to your virtualenv path if it differs from .venv/

VENV   ?= backend/.venv
PY     := $(abspath $(VENV))/bin/python
PIP    := $(VENV)/bin/pip
UV     := uv
PYTEST := $(VENV)/bin/pytest
RUFF   := $(VENV)/bin/ruff
MYPY   := $(VENV)/bin/mypy

.DEFAULT_GOAL := help

# -----------------------------------------------------------------------------
# Help
# -----------------------------------------------------------------------------
.PHONY: help
help:
	@echo ""
	@echo "  make install     Install all backend Python dependencies"
	@echo "  make dev         Start all services (docker-compose up -d)"
	@echo "  make stop        Stop all docker-compose services"
	@echo "  make migrate     Run Alembic migrations (upgrade head)"
	@echo "  make seed        Seed the database with demo hotel data (WIPES existing data)"
	@echo "  make ingest      Index the sample knowledge base (English + Nepali)"
	@echo "  make smoke       End-to-end smoke test against the running API"
	@echo "  make lint        Run ruff linter on backend"
	@echo "  make format      Auto-format backend code with ruff"
	@echo "  make typecheck   Run mypy --strict on backend app/"
	@echo "  make test        Run all pytest tests"
	@echo "  make test-cov    Run tests with coverage report"
	@echo "  make audit       Run pip-audit (dependency security scan)"
	@echo "  make ci          lint + typecheck + test (full CI check)"
	@echo "  make clean       Remove __pycache__, .mypy_cache, .ruff_cache"
	@echo ""

# -----------------------------------------------------------------------------
# Installation
# -----------------------------------------------------------------------------
.PHONY: install
install:
	cd backend && $(UV) venv .venv && $(UV) pip install -e ".[dev]"

# -----------------------------------------------------------------------------
# Docker
# -----------------------------------------------------------------------------
.PHONY: dev
dev:
	docker-compose up -d
	@echo "Services started. API: http://localhost:8000  Frontend: http://localhost:3000"

.PHONY: stop
stop:
	docker-compose down

.PHONY: build
build:
	docker-compose build

# -----------------------------------------------------------------------------
# Database
# -----------------------------------------------------------------------------
.PHONY: ingest
ingest:
	cd backend && $(PY) scripts/ingest_kb.py

.PHONY: smoke
smoke:
	cd backend && $(PY) scripts/smoke_test.py

.PHONY: migrate
migrate:
	cd backend && $(VENV)/bin/alembic upgrade head

.PHONY: migrate-down
migrate-down:
	cd backend && $(VENV)/bin/alembic downgrade -1

.PHONY: migrate-status
migrate-status:
	cd backend && $(VENV)/bin/alembic current

.PHONY: seed
seed:
	cd backend && $(PY) scripts/seed_db.py

# -----------------------------------------------------------------------------
# Code quality
# -----------------------------------------------------------------------------
.PHONY: lint
lint:
	cd backend && $(RUFF) check .

.PHONY: format
format:
	cd backend && $(RUFF) format .

.PHONY: typecheck
typecheck:
	cd backend && $(MYPY) --strict app/

.PHONY: audit
audit:
	cd backend && $(VENV)/bin/pip-audit

# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------
.PHONY: test
test:
	cd backend && $(PYTEST)

.PHONY: test-cov
test-cov:
	cd backend && $(PYTEST) \
		--cov=app/tools \
		--cov=app/agents \
		--cov=app/rag \
		--cov=app/utils \
		--cov-report=term-missing \
		--cov-report=html:htmlcov \
		--cov-fail-under=80

.PHONY: test-unit
test-unit:
	cd backend && $(PYTEST) -m unit

.PHONY: test-integration
test-integration:
	cd backend && $(PYTEST) -m integration

# -----------------------------------------------------------------------------
# CI — runs everything
# -----------------------------------------------------------------------------
.PHONY: ci
ci: lint typecheck test

# -----------------------------------------------------------------------------
# Cleanup
# -----------------------------------------------------------------------------
.PHONY: clean
clean:
	find backend -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; true
	find backend -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null; true
	find backend -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null; true
	find backend -type d -name "htmlcov"     -exec rm -rf {} + 2>/dev/null; true
	find backend -name "*.pyc" -delete 2>/dev/null; true
	@echo "Clean done."
