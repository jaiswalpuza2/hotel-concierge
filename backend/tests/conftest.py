"""Pytest fixtures shared across all tests.

Phase-specific fixtures (DB session, mock providers) are added in later phases.
"""
from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.utils.logger import configure_logging

# On Windows + Python 3.13, the default ProactorEventLoop causes spurious
# AttributeError crashes when TestClient closes connections. The Selector
# policy is fully compatible with all our async code.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Configure structlog once for the entire test session before any test runs.
configure_logging()


@pytest.fixture(scope="session")
def test_app() -> FastAPI:
    """Create a FastAPI test application instance."""
    return create_app()


@pytest.fixture(scope="session")
def client(test_app: FastAPI) -> Generator[TestClient, None, None]:
    """Synchronous test client (no real DB required for unit tests)."""
    with TestClient(test_app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(autouse=True)
def reset_settings_cache() -> Generator[None, None, None]:
    """Clear the lru_cache on get_settings() and all in-memory stores before each test."""
    # Always set a high rate limit during tests so integration tests never hit 429.
    # Unit rate-limit tests override this per-test with their own mini-apps.
    os.environ["RATE_LIMIT_PER_MINUTE"] = "10000"
    get_settings.cache_clear()
    # Clear in-memory JWT revocation store
    from app.auth.jwt import _revoked_jtis
    _revoked_jtis.clear()
    # Clear rate-limit sliding window store
    from app.middleware.rate_limit import _store
    _store.clear()
    yield
    get_settings.cache_clear()
    _revoked_jtis.clear()
    _store.clear()
