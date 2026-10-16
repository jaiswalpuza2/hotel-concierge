"""Request logging middleware.

Responsibilities:
- Generate a UUID ``request_id`` for every incoming HTTP request.
- Bind it (and an optional ``session_id`` from the query string) to the
  structlog context so every log line within that request carries both IDs.
- Inject ``X-Request-ID`` into the response headers.
- Emit a structured access log entry at the end of every request including
  method, path, status code, and duration in milliseconds.

Usage — registered in ``app/main.py``::

    app.add_middleware(RequestLoggingMiddleware)
"""
from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = structlog.get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that injects a request ID and logs every request."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Process the request, log it, and inject ``X-Request-ID``."""
        request_id = str(uuid.uuid4())

        # Optional session_id passed as a query param on WebSocket upgrades
        # and REST calls from the chat frontend.
        session_id: str = request.query_params.get("session_id", "")

        # Bind context vars for the lifetime of this request so every
        # structlog call within handlers automatically carries these fields.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            session_id=session_id or None,
            http_method=request.method,
            http_path=request.url.path,
        )

        start_time = time.perf_counter()
        status_code = 500  # default in case of unhandled exception

        try:
            response: Response = await call_next(request)
            status_code = response.status_code
        finally:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

            # Emit the access log entry at INFO level.
            # Skip /health pings to keep logs clean.
            if request.url.path != "/health":
                logger.info(
                    "http.request",
                    status_code=status_code,
                    duration_ms=duration_ms,
                )

            # Always clear context after the request completes.
            structlog.contextvars.clear_contextvars()

        # Attach the request ID to the response so callers can correlate logs.
        response.headers["X-Request-ID"] = request_id
        return response
