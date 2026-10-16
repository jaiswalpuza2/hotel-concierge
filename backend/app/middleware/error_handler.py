"""Global exception-to-HTTP-response middleware.

Maps every ``AppError`` subclass to its canonical HTTP status and JSON body.
Unhandled exceptions return 500 with a generic message — the full traceback
is logged internally and never leaked to the client.

Registration in ``main.py``::

    from app.middleware.error_handler import add_error_handlers
    add_error_handlers(app)

Design note:
    Starlette's ``add_exception_handler`` resolves handlers by iterating the
    registered types looking for an ``isinstance`` match.  We register the
    ``AppError`` base class which catches all subclasses because Starlette
    calls ``isinstance(exc, registered_type)`` for each handler in order.
    To guarantee our base handler fires *before* the generic ``Exception``
    fallback, ``AppError`` must be registered *after* ``Exception``
    (Starlette checks in reverse-registration order).
"""
from __future__ import annotations

import traceback
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.exceptions import AppError

logger = structlog.get_logger(__name__)


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    """Build the standard API error JSON response."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            }
        },
    )


async def _handle_app_error(request: Request, exc: Exception) -> JSONResponse:
    """Convert any AppError subclass to its HTTP status + JSON body."""
    if not isinstance(exc, AppError):
        # Should never happen given the handler registration, but be safe.
        return await _handle_unhandled_exception(request, exc)
    log_fn = logger.warning if exc.http_status < 500 else logger.error
    log_fn(
        "app.error",
        error_code=exc.code,
        error_message=exc.message,
        http_status=exc.http_status,
        details=exc.details,
    )
    return _error_response(
        status_code=exc.http_status,
        code=exc.code,
        message=exc.message,
        details=exc.details,
    )


async def _handle_validation_error(
    request: Request, exc: Exception
) -> JSONResponse:
    """Convert FastAPI/Pydantic request validation errors to 422 JSON."""
    if not isinstance(exc, RequestValidationError):
        return await _handle_unhandled_exception(request, exc)
    field_errors: list[dict[str, Any]] = []
    for error in exc.errors():
        field_errors.append(
            {
                "field": " -> ".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
        )
    logger.warning(
        "request.validation_error",
        field_errors=field_errors,
        path=request.url.path,
    )
    return _error_response(
        status_code=422,
        code="request_validation_error",
        message="Request body or parameters are invalid.",
        details={"fields": field_errors},
    )


async def _handle_http_exception(
    request: Request, exc: Exception
) -> JSONResponse:
    """Convert Starlette HTTP exceptions (404, 405, etc.) to JSON."""
    if not isinstance(exc, StarletteHTTPException):
        return await _handle_unhandled_exception(request, exc)
    logger.warning(
        "http.exception",
        status_code=exc.status_code,
        detail=exc.detail,
        path=request.url.path,
    )
    return _error_response(
        status_code=exc.status_code,
        code="http_error",
        message=str(exc.detail),
    )


async def _handle_unhandled_exception(
    request: Request, exc: Exception
) -> JSONResponse:
    """Catch-all for any unexpected exception.

    Logs the full traceback internally. Never leaks it to the client.
    """
    logger.error(
        "unhandled.exception",
        exc_type=type(exc).__name__,
        traceback=traceback.format_exc(),
        path=request.url.path,
        method=request.method,
    )
    return _error_response(
        status_code=500,
        code="internal_server_error",
        message="An unexpected error occurred. Please try again later.",
    )


def add_error_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the FastAPI application instance.

    Starlette iterates exception handlers in *reverse* registration order
    (last registered = checked first).  So we register from most generic
    to most specific: Exception first, AppError last.

    This ensures AppError is checked before the generic Exception fallback.
    """
    # 1. Generic fallback — checked last (registered first)
    app.add_exception_handler(Exception, _handle_unhandled_exception)  # type: ignore[arg-type]
    # 2. Starlette HTTP exceptions (404, 405, etc.)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)  # type: ignore[arg-type]
    # 3. FastAPI request validation errors
    app.add_exception_handler(RequestValidationError, _handle_validation_error)  # type: ignore[arg-type]
    # 4. Our AppError base class — checked first (registered last).
    #    Starlette checks isinstance(exc, registered_type) in reverse order,
    #    so AppError will match before Exception for any AppError subclass.
    app.add_exception_handler(AppError, _handle_app_error)  # type: ignore[arg-type]
