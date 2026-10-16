"""Unit tests for the sliding-window rate limiter middleware."""
from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from app.middleware.rate_limit import RateLimitMiddleware, _store
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient


def _make_rate_limited_app(limit: int = 5) -> FastAPI:
    """Return a tiny FastAPI app with a low rate limit for fast testing."""
    os.environ["RATE_LIMIT_PER_MINUTE"] = str(limit)

    from app.config import get_settings
    get_settings.cache_clear()

    mini = FastAPI()
    mini.add_middleware(RateLimitMiddleware)

    @mini.get("/ping")
    async def ping() -> JSONResponse:
        return JSONResponse({"pong": True})

    @mini.get("/health")
    async def health() -> JSONResponse:
        # Health is exempt from rate limiting
        return JSONResponse({"status": "ok"})

    return mini


@pytest.fixture(autouse=True)
def clear_rate_limit_store() -> Generator[None, None, None]:
    """Reset the in-memory rate-limit store before every test."""
    _store.clear()
    yield
    _store.clear()


class TestRateLimitMiddleware:
    def test_requests_within_limit_succeed(self) -> None:
        app = _make_rate_limited_app(limit=5)
        with TestClient(app, raise_server_exceptions=False) as client:
            for _ in range(5):
                r = client.get("/ping")
                assert r.status_code == 200

    def test_request_beyond_limit_returns_429(self) -> None:
        app = _make_rate_limited_app(limit=3)
        with TestClient(app, raise_server_exceptions=False) as client:
            for _ in range(3):
                client.get("/ping")
            r = client.get("/ping")
            assert r.status_code == 429

    def test_429_body_has_standard_shape(self) -> None:
        app = _make_rate_limited_app(limit=1)
        with TestClient(app, raise_server_exceptions=False) as client:
            client.get("/ping")
            r = client.get("/ping")
            assert r.status_code == 429
            body = r.json()
            assert body["error"]["code"] == "rate_limit_exceeded"
            assert "limit" in body["error"]["details"]
            assert "retry_after" in body["error"]["details"]

    def test_rate_limit_headers_present(self) -> None:
        app = _make_rate_limited_app(limit=10)
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.get("/ping")
            assert r.status_code == 200
            assert "X-RateLimit-Limit" in r.headers
            assert "X-RateLimit-Remaining" in r.headers
            assert "X-RateLimit-Reset" in r.headers
            assert r.headers["X-RateLimit-Limit"] == "10"

    def test_remaining_decrements(self) -> None:
        app = _make_rate_limited_app(limit=5)
        with TestClient(app, raise_server_exceptions=False) as client:
            r1 = client.get("/ping")
            r2 = client.get("/ping")
            remaining1 = int(r1.headers["X-RateLimit-Remaining"])
            remaining2 = int(r2.headers["X-RateLimit-Remaining"])
            assert remaining2 < remaining1

    def test_health_endpoint_exempt(self) -> None:
        """Health check endpoint must never be rate limited."""
        app = _make_rate_limited_app(limit=1)
        with TestClient(app, raise_server_exceptions=False) as client:
            # Exhaust the limit on /ping
            client.get("/ping")
            client.get("/ping")
            # /health should still return 200
            for _ in range(5):
                r = client.get("/health")
                assert r.status_code == 200

    def test_429_includes_retry_after_header(self) -> None:
        app = _make_rate_limited_app(limit=1)
        with TestClient(app, raise_server_exceptions=False) as client:
            client.get("/ping")
            r = client.get("/ping")
            assert r.status_code == 429
            assert "Retry-After" in r.headers
