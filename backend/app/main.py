"""FastAPI application factory for the Concierge platform.

This module is the single wiring point for:
- Application lifecycle (lifespan context manager)
- Middleware registration (logging, rate limiting, CORS)
- Exception handler registration
- Router mounting

Import order matters: logging must be configured before any other module
uses ``structlog.get_logger``, so ``configure_logging()`` is called first
inside the lifespan startup block.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.runtime import build_runtime
from app.api.v1.health import router as health_router
from app.api.v1.router import api_router
from app.api.ws.chat import router as ws_router
from app.config import get_settings
from app.db.base import async_session_factory
from app.middleware.error_handler import add_error_handlers
from app.middleware.logging import RequestLoggingMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.utils.logger import configure_logging

# Configure structlog before the module-level logger is created.
configure_logging()

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: build the concierge runtime on startup, release it on shutdown."""
    settings = get_settings()
    if settings.jwt_secret_key.get_secret_value() in ("", "CHANGE_ME", "change-me"):
        if settings.app_env == "production":
            raise RuntimeError("JWT_SECRET_KEY must be set to a long random value in production")
        logger.warning("security.default_jwt_secret", hint="set JWT_SECRET_KEY before deploying")
    logger.info(
        "concierge.startup",
        env=settings.app_env,
        business=settings.business_name,
        business_type=settings.business_type,
        llm=settings.llm_provider,
    )
    runtime = await build_runtime(async_session_factory, settings.db_url)
    app.state.runtime = runtime
    try:
        yield
    finally:
        await runtime.close()
        logger.info("concierge.shutdown")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance.

    Returns:
        A fully configured FastAPI application ready to be served by uvicorn.
    """
    settings = get_settings()

    app = FastAPI(
        title=f"{settings.business_name} — AI Concierge API",
        version="1.0.0",
        description=(
            "Autonomous multi-agent AI concierge: bilingual chat & voice, "
            "RAG knowledge base, real-time booking tools, human handoff."
        ),
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url="/redoc" if settings.app_env != "production" else None,
        openapi_url="/openapi.json" if settings.app_env != "production" else None,
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------
    # Exception handlers — registered before middleware so they fire even
    # on errors raised inside middleware.
    # ------------------------------------------------------------------
    add_error_handlers(app)

    # ------------------------------------------------------------------
    # Middleware — registered in reverse order (last added = outermost).
    # Execution order for a request: CORS -> RequestLogging -> RateLimit -> handler
    # ------------------------------------------------------------------

    # 1. Rate limiting
    app.add_middleware(RateLimitMiddleware)

    # 2. Request ID injection + structured access logging
    app.add_middleware(RequestLoggingMiddleware)

    # 3. CORS - added LAST so it is OUTERMOST (Starlette wraps in reverse order). This makes
    #    even 429 and 500 responses carry CORS headers and lets preflight requests through.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # Routers
    # ------------------------------------------------------------------

    # /health — root level (no /api/v1 prefix), excluded from rate limiting
    app.include_router(health_router)

    # /api/v1/* — all other versioned routes
    app.include_router(api_router, prefix="/api/v1")

    # /ws/chat - real-time chat and voice
    app.include_router(ws_router)

    return app


# Module-level app instance used by uvicorn and tests.
app = create_app()
