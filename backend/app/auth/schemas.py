"""Pydantic schemas for authentication request / response bodies."""
from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    """Body for POST /api/v1/auth/login."""

    # Use str + custom validator instead of EmailStr to allow .local domains
    # in development (email-validator rejects special-use TLDs like .local).
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def basic_email_format(cls, v: str) -> str:
        """Ensure email contains @ and a dot after it."""
        if "@" not in v or "." not in v.split("@", 1)[1]:
            raise ValueError("Invalid email format")
        return v.lower().strip()


class TokenPayload(BaseModel):
    """Claims embedded in every JWT.

    ``sub``   — subject: the user's UUID as a string.
    ``role``  — the user's role (admin | staff).
    ``type``  — token type (access | refresh) to prevent token reuse attacks.
    ``jti``   — JWT ID: unique identifier used for refresh-token revocation.
    ``exp``   — expiry (set by python-jose, validated on decode).
    """

    sub: str  # user UUID as string
    role: Literal["admin", "staff"]
    type: Literal["access", "refresh"]
    jti: str  # unique token ID


class TokenResponse(BaseModel):
    """Response body for login and refresh endpoints."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # access token TTL in seconds


class AccessTokenResponse(BaseModel):
    """Response body for the refresh endpoint (access token only)."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    """Slim user representation returned alongside tokens."""

    id: uuid.UUID
    email: str
    role: Literal["admin", "staff"]


class LoginResponse(BaseModel):
    """Full login response including the user profile."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class RefreshRequest(BaseModel):
    """Body for POST /api/v1/auth/refresh."""

    refresh_token: str
