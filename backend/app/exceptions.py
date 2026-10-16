"""Custom exception hierarchy for the Concierge application.

All application-level exceptions inherit from ``AppError``.
The global error handler in ``app/middleware/error_handler.py`` maps each
subclass to its canonical HTTP status code and serialises it as JSON.

Usage::

    from app.exceptions import NotFoundError
    raise NotFoundError("Booking not found", details={"booking_id": booking_id})

The caller (agent loop, route handler, tool function) never needs to know the
HTTP status code — the middleware handles the mapping.
"""
from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for all application errors.

    Args:
        message: Human-readable description of the error. Shown to the client.
        code: Machine-readable slug, e.g. ``"booking_not_found"``. Used by
            the frontend and agent code to take action on specific errors.
        details: Optional dict with additional context (IDs, field names, etc).
            Never put secrets or stack traces here — this goes in the response.
        http_status: HTTP status code. Defaults to 500; subclasses set their
            own canonical values.
    """

    http_status: int = 500

    def __init__(
        self,
        message: str,
        *,
        code: str = "internal_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialise to the standard API error body."""
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


# ---------------------------------------------------------------------------
# 400 – Bad Request / Validation
# ---------------------------------------------------------------------------


class ValidationError(AppError):
    """Input failed schema or business-rule validation.

    Use when Pydantic model validation fails inside a tool function, or when
    a value is structurally valid but violates a business rule
    (e.g. check_out <= check_in).
    """

    http_status = 400

    def __init__(
        self,
        message: str = "Validation failed",
        *,
        code: str = "validation_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, details=details)


# ---------------------------------------------------------------------------
# 401 – Unauthorised
# ---------------------------------------------------------------------------


class AuthError(AppError):
    """Authentication failed or token is invalid / expired."""

    http_status = 401

    def __init__(
        self,
        message: str = "Authentication required",
        *,
        code: str = "auth_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, details=details)


# ---------------------------------------------------------------------------
# 403 – Forbidden
# ---------------------------------------------------------------------------


class PermissionError(AppError):
    """Authenticated user lacks permission to perform the requested action."""

    http_status = 403

    def __init__(
        self,
        message: str = "Permission denied",
        *,
        code: str = "permission_denied",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, details=details)


# ---------------------------------------------------------------------------
# 404 – Not Found
# ---------------------------------------------------------------------------


class NotFoundError(AppError):
    """The requested resource does not exist."""

    http_status = 404

    def __init__(
        self,
        message: str = "Resource not found",
        *,
        code: str = "not_found",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, details=details)


# ---------------------------------------------------------------------------
# 409 – Conflict
# ---------------------------------------------------------------------------


class ConflictError(AppError):
    """The request conflicts with the current state of the resource.

    Primary use case: double-booking guard — the room is no longer available
    by the time the transaction commits.
    """

    http_status = 409

    def __init__(
        self,
        message: str = "Resource conflict",
        *,
        code: str = "conflict",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, details=details)


# ---------------------------------------------------------------------------
# 500 – Internal errors (subclasses of AppError for structured logging)
# ---------------------------------------------------------------------------


class ToolError(AppError):
    """A database tool function failed after exhausting retries."""

    http_status = 500

    def __init__(
        self,
        message: str = "Tool execution failed",
        *,
        code: str = "tool_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, details=details)


class IngestionError(AppError):
    """Document ingestion failed (load, split, embed, or store step)."""

    http_status = 500

    def __init__(
        self,
        message: str = "Document ingestion failed",
        *,
        code: str = "ingestion_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, details=details)


# ---------------------------------------------------------------------------
# 502 – Bad Gateway (external provider failures)
# ---------------------------------------------------------------------------


class ProviderError(AppError):
    """An external provider (LLM, SMS, Email, STT, TTS) returned an error."""

    http_status = 502

    def __init__(
        self,
        message: str = "External provider error",
        *,
        code: str = "provider_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, details=details)


# ---------------------------------------------------------------------------
# 429 – Too Many Requests
# ---------------------------------------------------------------------------


class RateLimitError(AppError):
    """The client has exceeded the configured request rate limit."""

    http_status = 429

    def __init__(
        self,
        message: str = "Too many requests. Please slow down.",
        *,
        code: str = "rate_limit_exceeded",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, details=details)
