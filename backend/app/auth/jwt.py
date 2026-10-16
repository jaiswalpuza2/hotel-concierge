"""JWT token creation, verification, and refresh-token revocation.

Access tokens are short-lived (15 min by default).
Refresh tokens are long-lived (7 days) and stored in an HTTP-only cookie.

Revocation strategy: we store the JTI (JWT ID) of revoked refresh tokens in
the database table ``revoked_tokens``.  For Phase 1 we use a simple in-memory
set (reset on restart); Phase 2 will persist this to Redis or the DB.  The
access token TTL is short enough that it need not be revoked individually.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from jose import ExpiredSignatureError, JWTError, jwt

from app.auth.schemas import TokenPayload
from app.config import Settings, get_settings
from app.exceptions import AuthError

logger = structlog.get_logger(__name__)


def _settings() -> Settings:
    """Return settings (thin wrapper so callers don't import get_settings)."""
    return get_settings()

# In-memory revocation store for refresh token JTIs.
# Replaced with a DB/Redis-backed store in production.
_revoked_jtis: set[str] = set()


def create_access_token(user_id: uuid.UUID, role: str) -> tuple[str, int]:
    """Create a signed JWT access token.

    Args:
        user_id: The user's primary key UUID.
        role: The user's role string (admin | staff).

    Returns:
        Tuple of (encoded_jwt, expires_in_seconds).
    """
    settings = _settings()
    expire_seconds = settings.access_token_expire_minutes * 60
    now = datetime.now(tz=UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(seconds=expire_seconds),
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    return token, expire_seconds


def create_refresh_token(user_id: uuid.UUID, role: str) -> tuple[str, str]:
    """Create a signed JWT refresh token.

    Args:
        user_id: The user's primary key UUID.
        role: The user's role string.

    Returns:
        Tuple of (encoded_jwt, jti) so the JTI can be stored for revocation.
    """
    settings = _settings()
    now = datetime.now(tz=UTC)
    jti = str(uuid.uuid4())
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "refresh",
        "jti": jti,
        "iat": now,
        "exp": now + timedelta(days=settings.refresh_token_expire_days),
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    return token, jti


def decode_token(token: str) -> TokenPayload:
    """Decode and validate a JWT (access or refresh).

    Validates signature, expiry, and that the JTI has not been revoked.

    Args:
        token: The raw JWT string from the Authorization header or cookie.

    Returns:
        A ``TokenPayload`` with the claims.

    Raises:
        AuthError: If the token is expired, invalid, or has been revoked.
    """
    settings = _settings()
    try:
        raw = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
    except ExpiredSignatureError:
        raise AuthError("Token has expired", code="token_expired") from None
    except JWTError as exc:
        logger.warning("jwt.invalid_token", error=str(exc))
        raise AuthError("Invalid token", code="token_invalid") from exc

    # Check revocation for refresh tokens
    jti: str = raw.get("jti", "")
    if jti in _revoked_jtis:
        raise AuthError("Token has been revoked", code="token_revoked")

    try:
        return TokenPayload(
            sub=raw["sub"],
            role=raw["role"],
            type=raw["type"],
            jti=jti,
        )
    except (KeyError, ValueError) as exc:
        raise AuthError("Token payload is malformed", code="token_invalid") from exc


def decode_access_token(token: str) -> TokenPayload:
    """Decode a token and assert it is an access token.

    Raises:
        AuthError: If the token is a refresh token (prevent token-type abuse).
    """
    payload = decode_token(token)
    if payload.type != "access":
        raise AuthError(
            "Expected an access token",
            code="wrong_token_type",
            details={"got": payload.type},
        )
    return payload


def decode_refresh_token(token: str) -> TokenPayload:
    """Decode a token and assert it is a refresh token."""
    payload = decode_token(token)
    if payload.type != "refresh":
        raise AuthError(
            "Expected a refresh token",
            code="wrong_token_type",
            details={"got": payload.type},
        )
    return payload


def revoke_refresh_token(jti: str) -> None:
    """Add a refresh token JTI to the revocation store.

    Args:
        jti: The JWT ID from the token being revoked (e.g. on logout).
    """
    _revoked_jtis.add(jti)
    logger.info("jwt.refresh_token_revoked", jti=jti[:8] + "...")
