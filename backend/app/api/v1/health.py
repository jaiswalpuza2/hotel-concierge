"""Health check endpoint.

GET /health returns the operational status of the API and its dependencies.
It is used by:
- Docker healthcheck (``curl -f http://localhost:8000/health``)
- Load balancer health probes
- The admin dashboard's connection indicator

The endpoint is exempt from authentication and rate limiting.
"""
from __future__ import annotations

from typing import Literal

import structlog
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.config import get_settings
from app.db.base import async_session_factory

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["health"])

# Application version — single source of truth.
APP_VERSION = "1.0.0"


class HealthResponse(BaseModel):
    """Shape of the health check response body."""

    status: Literal["ok", "degraded"]
    db: Literal["ok", "degraded"]
    version: str


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns the operational status of the API and its database connection.",
    # Exclude from OpenAPI authentication requirement
    include_in_schema=True,
)
async def health_check() -> JSONResponse:
    """Ping the database and return overall service health.

    Returns:
        200 with ``{"status": "ok"}`` when all dependencies are healthy.
        503 with ``{"status": "degraded"}`` when the DB is unreachable.
    """
    settings = get_settings()
    db_status: Literal["ok", "degraded"] = "ok"

    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("health.db_unreachable", error=str(exc))
        db_status = "degraded"

    overall: Literal["ok", "degraded"] = "ok" if db_status == "ok" else "degraded"
    http_status = 200 if overall == "ok" else 503

    return JSONResponse(
        status_code=http_status,
        content={
            "status": overall,
            "db": db_status,
            "version": APP_VERSION,
            "business": settings.business_name,
        },
    )
