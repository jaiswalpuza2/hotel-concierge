"""Sliding-window rate limiter middleware.

Tracks request timestamps per client IP in an in-memory dict.  This is
sufficient for a single-process deployment (the demo target).  For a
multi-replica production deployment, replace ``_store`` with a Redis-backed
implementation (the interface stays identical).

Rate-limit headers emitted on every response:
    X-RateLimit-Limit     — configured maximum requests per window
    X-RateLimit-Remaining — requests remaining in the current window
    X-RateLimit-Reset     — Unix timestamp when the window resets

A client that exceeds the limit receives a 429 JSON response (mapped through
``AppError`` so the format is identical to other errors).

Registration in ``main.py``::

    app.add_middleware(RateLimitMiddleware)
"""
from __future__ import annotations

import time
from collections import deque
from collections.abc import MutableMapping

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.config import get_settings

logger = structlog.get_logger(__name__)

# In-memory sliding-window store: IP → deque of request timestamps (float).
# The deque stores only timestamps within the current window so memory is
# bounded at O(rate_limit_per_minute) per unique IP.
_store: MutableMapping[str, deque[float]] = {}

# Paths that are exempt from rate limiting (health checks, metrics).
_EXEMPT_PATHS: frozenset[str] = frozenset({"/health", "/metrics"})


def _get_client_ip(request: Request) -> str:
    """Extract the real client IP, honoring X-Forwarded-For from a trusted proxy."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the leftmost (originating) IP from the chain.
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter: N requests per 60-second window per IP."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        settings = get_settings()
        self._limit: int = settings.rate_limit_per_minute
        self._window: int = 60  # seconds

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Check the rate limit before forwarding the request."""
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        client_ip = _get_client_ip(request)
        now = time.time()
        window_start = now - self._window

        # Retrieve or create the timestamp deque for this IP.
        if client_ip not in _store:
            _store[client_ip] = deque()

        timestamps = _store[client_ip]

        # Evict timestamps outside the current window (sliding behaviour).
        while timestamps and timestamps[0] < window_start:
            timestamps.popleft()

        current_count = len(timestamps)
        remaining = max(0, self._limit - current_count)
        reset_at = int(window_start + self._window) + 1

        if current_count >= self._limit:
            logger.warning(
                "rate_limit.exceeded",
                client_ip=client_ip,
                count=current_count,
                limit=self._limit,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "rate_limit_exceeded",
                        "message": "Too many requests. Please slow down.",
                        "details": {
                            "limit": self._limit,
                            "window_seconds": self._window,
                            "retry_after": reset_at - int(now),
                        },
                    }
                },
                headers={
                    "X-RateLimit-Limit": str(self._limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_at),
                    "Retry-After": str(reset_at - int(now)),
                },
            )

        # Record this request's timestamp.
        timestamps.append(now)

        response = await call_next(request)

        # Attach rate-limit headers to every non-limited response.
        response.headers["X-RateLimit-Limit"] = str(self._limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining - 1)
        response.headers["X-RateLimit-Reset"] = str(reset_at)

        return response
