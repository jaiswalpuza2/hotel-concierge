"""FastAPI dependency functions.

These are injected via ``Depends()`` in route handlers and WebSocket endpoints.
Keeping them here avoids circular imports and makes mocking in tests trivial.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Literal

import structlog
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import decode_access_token
from app.auth.schemas import TokenPayload
from app.db.base import get_db_session
from app.db.models.user import User
from app.exceptions import AuthError, PermissionError, ProviderError

logger = structlog.get_logger(__name__)

# Reusable bearer scheme — auto-generates the lock icon in OpenAPI docs
_bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Database session
# ---------------------------------------------------------------------------


async def get_db(
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
) -> AsyncIterator[AsyncSession]:
    """Yield a DB session. Thin alias so routes import only from dependencies."""
    yield session


# ---------------------------------------------------------------------------
# JWT authentication
# ---------------------------------------------------------------------------


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),  # noqa: B008
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
) -> User:
    """Extract and validate the Bearer JWT, return the authenticated User.

    Used as a FastAPI dependency on every protected route::

        @router.get("/bookings")
        async def list_bookings(user: User = Depends(get_current_user)):
            ...

    Raises:
        AuthError (401): If the token is missing, invalid, or the user no
            longer exists / is inactive.
    """
    if credentials is None:
        raise AuthError(
            "Authentication required",
            code="missing_token",
            details={"hint": "Provide a Bearer token in the Authorization header"},
        )

    payload: TokenPayload = decode_access_token(credentials.credentials)

    result = await session.execute(
        select(User).where(User.id == uuid.UUID(payload.sub))
    )
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise AuthError("User not found or inactive", code="invalid_credentials")

    logger.debug("auth.user_authenticated", user_id=str(user.id), role=user.role)
    return user


# ---------------------------------------------------------------------------
# Role-based access control
# ---------------------------------------------------------------------------


def require_role(
    *allowed_roles: Literal["admin", "staff"],
) -> type[User]:
    """Factory that returns a dependency enforcing one of the given roles.

    Usage::

        @router.delete("/documents/{id}")
        async def delete_doc(user: User = Depends(require_role("admin"))):
            ...

    Raises:
        PermissionError (403): If the authenticated user's role is not in
            ``allowed_roles``.
    """
    async def _check_role(
        user: User = Depends(get_current_user),  # noqa: B008
    ) -> User:
        if user.role not in allowed_roles:
            raise PermissionError(
                f"This action requires one of these roles: {', '.join(allowed_roles)}",
                code="insufficient_role",
                details={"required": list(allowed_roles), "current": user.role},
            )
        return user

    return _check_role  # type: ignore[return-value]


def get_runtime(request: Request):  # type: ignore[no-untyped-def]
    """Return the application runtime (chat service, handoff service, WS manager)."""
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        raise ProviderError("Service is starting up", code="runtime_not_ready")
    return runtime
