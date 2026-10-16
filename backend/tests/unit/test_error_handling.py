"""Unit tests for custom exceptions and the global error handler.

These tests use the FastAPI TestClient so they exercise the full middleware
stack without requiring a real database connection.
"""
from __future__ import annotations

from collections.abc import Generator

import pytest
from app.exceptions import (
    AppError,
    AuthError,
    ConflictError,
    IngestionError,
    NotFoundError,
    ProviderError,
    RateLimitError,
    ToolError,
    ValidationError,
)
from app.middleware.error_handler import add_error_handlers
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers: tiny FastAPI app with test routes that raise our exceptions
# ---------------------------------------------------------------------------


def _make_test_app() -> FastAPI:
    """Return a minimal FastAPI app with routes that raise each exception type."""
    mini = FastAPI()
    add_error_handlers(mini)

    @mini.get("/raise/validation")
    async def raise_validation() -> None:
        raise ValidationError("bad input", details={"field": "check_in"})

    @mini.get("/raise/auth")
    async def raise_auth() -> None:
        raise AuthError("invalid token")

    @mini.get("/raise/notfound")
    async def raise_notfound() -> None:
        raise NotFoundError("booking not found", details={"booking_id": "abc"})

    @mini.get("/raise/conflict")
    async def raise_conflict() -> None:
        raise ConflictError("room already booked")

    @mini.get("/raise/tool")
    async def raise_tool() -> None:
        raise ToolError("db timeout")

    @mini.get("/raise/ingestion")
    async def raise_ingestion() -> None:
        raise IngestionError("pdf parse failed")

    @mini.get("/raise/provider")
    async def raise_provider() -> None:
        raise ProviderError("LLM API 503", details={"provider": "openai"})

    @mini.get("/raise/ratelimit")
    async def raise_ratelimit() -> None:
        raise RateLimitError()

    return mini


def _make_unhandled_app() -> FastAPI:
    """App that raises a raw RuntimeError (not an AppError)."""
    mini = FastAPI()
    add_error_handlers(mini)

    @mini.get("/raise/unhandled")
    async def raise_unhandled() -> None:
        raise RuntimeError("something completely unexpected")

    return mini


@pytest.fixture(scope="module")
def error_client() -> Generator[TestClient, None, None]:
    # raise_server_exceptions=True: AppError is caught by our handler before
    # it propagates — the client receives the JSON response, not an exception.
    with TestClient(_make_test_app(), raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# Exception hierarchy tests
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    def test_app_error_base(self) -> None:
        err = AppError("base error", code="base", details={"k": "v"})
        assert err.message == "base error"
        assert err.code == "base"
        assert err.details == {"k": "v"}
        assert err.http_status == 500

    def test_validation_error_defaults(self) -> None:
        err = ValidationError()
        assert err.http_status == 400
        assert err.code == "validation_error"

    def test_auth_error(self) -> None:
        err = AuthError("bad token")
        assert err.http_status == 401

    def test_not_found_error(self) -> None:
        err = NotFoundError("missing")
        assert err.http_status == 404

    def test_conflict_error(self) -> None:
        err = ConflictError("dupe")
        assert err.http_status == 409

    def test_tool_error(self) -> None:
        assert ToolError().http_status == 500

    def test_provider_error(self) -> None:
        assert ProviderError().http_status == 502

    def test_to_dict(self) -> None:
        err = NotFoundError("booking not found", details={"id": "123"})
        d = err.to_dict()
        assert d["error"]["code"] == "not_found"
        assert d["error"]["message"] == "booking not found"
        assert d["error"]["details"]["id"] == "123"


# ---------------------------------------------------------------------------
# HTTP response mapping tests
# ---------------------------------------------------------------------------


class TestErrorHandlerHTTPMapping:
    def test_validation_returns_400(self, error_client: TestClient) -> None:
        r = error_client.get("/raise/validation")
        assert r.status_code == 400
        body = r.json()
        assert body["error"]["code"] == "validation_error"
        assert "field" in body["error"]["details"]

    def test_auth_returns_401(self, error_client: TestClient) -> None:
        r = error_client.get("/raise/auth")
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "auth_error"

    def test_notfound_returns_404(self, error_client: TestClient) -> None:
        r = error_client.get("/raise/notfound")
        assert r.status_code == 404
        assert r.json()["error"]["details"]["booking_id"] == "abc"

    def test_conflict_returns_409(self, error_client: TestClient) -> None:
        r = error_client.get("/raise/conflict")
        assert r.status_code == 409

    def test_tool_returns_500(self, error_client: TestClient) -> None:
        r = error_client.get("/raise/tool")
        assert r.status_code == 500

    def test_ingestion_returns_500(self, error_client: TestClient) -> None:
        r = error_client.get("/raise/ingestion")
        assert r.status_code == 500

    def test_provider_returns_502(self, error_client: TestClient) -> None:
        r = error_client.get("/raise/provider")
        assert r.status_code == 502
        assert r.json()["error"]["details"]["provider"] == "openai"

    def test_ratelimit_returns_429(self, error_client: TestClient) -> None:
        r = error_client.get("/raise/ratelimit")
        assert r.status_code == 429

    def test_unhandled_returns_500_no_traceback(self) -> None:
        """RuntimeError must be caught, return JSON 500, and not expose traceback."""
        with TestClient(_make_unhandled_app(), raise_server_exceptions=False) as c:
            r = c.get("/raise/unhandled")
        assert r.status_code == 500
        body = r.json()
        assert body["error"]["code"] == "internal_server_error"
        # Stack trace must NOT appear in the response body
        assert "Traceback" not in body["error"]["message"]
        assert "traceback" not in body["error"].get("details", {})

    def test_error_response_shape(self, error_client: TestClient) -> None:
        """All error responses must have the standard shape."""
        r = error_client.get("/raise/validation")
        body = r.json()
        assert "error" in body
        assert "code" in body["error"]
        assert "message" in body["error"]
        assert "details" in body["error"]
