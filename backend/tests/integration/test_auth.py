"""Integration tests for the auth API endpoints.

We test auth logic against a real FastAPI app but mock the DB session
to avoid the asyncpg event-loop-reuse error on Windows + Python 3.13.
The DB session is only needed to look up users; we inject a seeded user
directly so the test logic is identical to a real DB call.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.auth.jwt import (
    decode_access_token,
)
from app.auth.password import hash_password
from app.db.models.user import User
from app.main import create_app
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _make_mock_user(role: str = "admin", email: str = "admin@hotel.local") -> User:
    """Return a User ORM instance with bcrypt-hashed password (no DB needed)."""
    user = MagicMock(spec=User)
    user.id = ADMIN_ID if role == "admin" else uuid.uuid4()
    user.email = email
    user.role = role
    user.is_active = True
    user.hashed_password = hash_password("Admin@2081" if role == "admin" else "Staff@2081")
    return user


def _make_app_with_mock_db(mock_user: User | None) -> FastAPI:
    """Create a FastAPI app where the DB session returns mock_user on User query."""
    from app.db.base import get_db_session

    async def mock_db_session() -> AsyncIterator[AsyncSession]:
        """Fake DB session that returns our mock user."""
        sess = AsyncMock(spec=AsyncSession)
        # Simulate: result = await session.execute(select(User)...)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = mock_user
        sess.execute = AsyncMock(return_value=result_mock)
        yield sess

    app = create_app()
    app.dependency_overrides[get_db_session] = mock_db_session
    return app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_client() -> TestClient:
    """TestClient with admin user returned from mock DB."""
    app = _make_app_with_mock_db(_make_mock_user("admin"))
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture
def staff_client() -> TestClient:
    """TestClient with staff user returned from mock DB."""
    app = _make_app_with_mock_db(_make_mock_user("staff", "staff@hotel.local"))
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture
def no_user_client() -> TestClient:
    """TestClient where the mock DB returns None (user not found)."""
    app = _make_app_with_mock_db(None)
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# Login tests
# ---------------------------------------------------------------------------


class TestLogin:
    def test_login_valid_credentials(self, admin_client: TestClient) -> None:
        r = admin_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@hotel.local", "password": "Admin@2081"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"
        assert body["expires_in"] > 0
        assert body["user"]["email"] == "admin@hotel.local"
        assert body["user"]["role"] == "admin"

    def test_login_wrong_password(self, admin_client: TestClient) -> None:
        r = admin_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@hotel.local", "password": "WrongPassword"},
        )
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "invalid_credentials"

    def test_login_user_not_found(self, no_user_client: TestClient) -> None:
        r = no_user_client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@hotel.local", "password": "anything"},
        )
        assert r.status_code == 401

    def test_login_missing_email_returns_422(self, admin_client: TestClient) -> None:
        r = admin_client.post("/api/v1/auth/login", json={"password": "Admin@2081"})
        assert r.status_code == 422

    def test_login_staff_user(self, staff_client: TestClient) -> None:
        r = staff_client.post(
            "/api/v1/auth/login",
            json={"email": "staff@hotel.local", "password": "Staff@2081"},
        )
        assert r.status_code == 200
        assert r.json()["user"]["role"] == "staff"


# ---------------------------------------------------------------------------
# Refresh tests
# ---------------------------------------------------------------------------


class TestRefresh:
    def test_refresh_with_valid_token(self, admin_client: TestClient) -> None:
        login = admin_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@hotel.local", "password": "Admin@2081"},
        )
        r = admin_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": login.json()["refresh_token"]},
        )
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_refresh_with_access_token_fails(self, admin_client: TestClient) -> None:
        login = admin_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@hotel.local", "password": "Admin@2081"},
        )
        r = admin_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": login.json()["access_token"]},
        )
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "wrong_token_type"

    def test_refresh_with_garbage_token_fails(self, admin_client: TestClient) -> None:
        r = admin_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "not.a.valid.jwt"},
        )
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Logout tests
# ---------------------------------------------------------------------------


class TestLogout:
    def test_logout_revokes_refresh_token(self, admin_client: TestClient) -> None:
        login = admin_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@hotel.local", "password": "Admin@2081"},
        )
        refresh_token = login.json()["refresh_token"]

        r = admin_client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
        assert r.status_code == 204

        r2 = admin_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
        )
        assert r2.status_code == 401
        assert r2.json()["error"]["code"] == "token_revoked"

    def test_logout_already_revoked_returns_204(self, admin_client: TestClient) -> None:
        login = admin_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@hotel.local", "password": "Admin@2081"},
        )
        refresh_token = login.json()["refresh_token"]
        admin_client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
        r = admin_client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
        assert r.status_code == 204


# ---------------------------------------------------------------------------
# Protected route dependency tests
# ---------------------------------------------------------------------------


class TestProtectedRoutes:
    def test_health_is_public(self, admin_client: TestClient) -> None:
        r = admin_client.get("/health")
        assert r.status_code in (200, 503)

    def test_access_token_has_correct_claims(self, admin_client: TestClient) -> None:
        login = admin_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@hotel.local", "password": "Admin@2081"},
        )
        token = login.json()["access_token"]
        payload = decode_access_token(token)
        assert payload.role == "admin"
        assert payload.type == "access"

    def test_wrong_method_returns_405(self, admin_client: TestClient) -> None:
        r = admin_client.get("/api/v1/auth/login")
        assert r.status_code == 405
