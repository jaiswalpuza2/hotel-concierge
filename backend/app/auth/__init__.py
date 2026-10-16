"""Authentication package — JWT, password hashing, and Pydantic schemas."""
from __future__ import annotations

from app.auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    revoke_refresh_token,
)
from app.auth.password import hash_password, verify_password
from app.auth.schemas import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    TokenPayload,
    TokenResponse,
    UserResponse,
)

__all__ = [
    "create_access_token",
    "create_refresh_token",
    "decode_access_token",
    "decode_refresh_token",
    "revoke_refresh_token",
    "hash_password",
    "verify_password",
    "LoginRequest",
    "LoginResponse",
    "RefreshRequest",
    "TokenPayload",
    "TokenResponse",
    "UserResponse",
]
