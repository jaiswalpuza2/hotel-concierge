"""Authentication endpoints.

POST /api/v1/auth/login   -- exchange credentials for tokens
POST /api/v1/auth/refresh -- exchange refresh token for new access token
POST /api/v1/auth/logout  -- revoke refresh token
"""
from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    revoke_refresh_token,
)
from app.auth.password import verify_password
from app.auth.schemas import (
    AccessTokenResponse,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    UserResponse,
)
from app.db.base import get_db_session
from app.db.models.user import User
from app.exceptions import AuthError

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["auth"])


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Login with email and password",
)
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
) -> JSONResponse:
    """Authenticate a user and return access + refresh tokens.

    The refresh token should be stored in an HTTP-only cookie by the client.
    The access token is stored in memory (not localStorage) to reduce XSS risk.

    Raises:
        AuthError (401): If credentials are incorrect or account is inactive.
    """
    # Look up user by email
    result = await session.execute(
        select(User).where(User.email == body.email)
    )
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        # Identical error for both wrong email and inactive account
        # to prevent user enumeration
        raise AuthError(
            "Invalid email or password",
            code="invalid_credentials",
        )

    if not verify_password(body.password, user.hashed_password):
        logger.warning("auth.login_failed", email=body.email[:4] + "***")
        raise AuthError(
            "Invalid email or password",
            code="invalid_credentials",
        )

    access_token, expires_in = create_access_token(user.id, user.role)
    refresh_token, _jti = create_refresh_token(user.id, user.role)

    logger.info("auth.login_success", user_id=str(user.id), role=user.role)

    return JSONResponse(
        status_code=200,
        content=LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=expires_in,
            user=UserResponse(
                id=user.id,
                email=user.email,
                role=user.role,  # type: ignore[arg-type]
            ),
        ).model_dump(mode="json"),
    )


@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    summary="Exchange a refresh token for a new access token",
)
async def refresh(
    body: RefreshRequest,
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
) -> JSONResponse:
    """Issue a new access token given a valid refresh token.

    The refresh token is NOT rotated (single-rotation adds complexity for
    the demo; noted in memory.md as a production hardening item).

    Raises:
        AuthError (401): If the refresh token is invalid, expired, or revoked.
    """
    payload = decode_refresh_token(body.refresh_token)

    # Verify the user still exists and is active
    result = await session.execute(
        select(User).where(User.id == uuid.UUID(payload.sub))
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise AuthError("User not found or inactive", code="invalid_credentials")

    access_token, expires_in = create_access_token(user.id, user.role)
    logger.info("auth.token_refreshed", user_id=str(user.id))

    return JSONResponse(
        status_code=200,
        content=AccessTokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=expires_in,
        ).model_dump(),
    )


@router.post(
    "/logout",
    status_code=204,
    response_class=Response,
    summary="Revoke a refresh token (logout)",
)
async def logout(body: RefreshRequest) -> Response:
    """Revoke the supplied refresh token so it cannot be used again.

    The client must discard its stored access token.
    Returns 204 No Content on success.

    Note: We return 204 even if the token is already revoked or expired,
    to prevent information leakage about token state.
    """
    try:
        payload = decode_refresh_token(body.refresh_token)
        revoke_refresh_token(payload.jti)
        logger.info("auth.logout", user_id=payload.sub[:8] + "...")
    except AuthError:
        pass
    return Response(status_code=204)
