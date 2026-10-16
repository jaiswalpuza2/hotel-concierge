"""Structlog JSON logger factory.

Call ``configure_logging()`` once at application startup (in ``main.py``).
Then obtain a logger anywhere with ``structlog.get_logger(__name__)``.

Every log record automatically carries the fields set on the current context
via ``structlog.contextvars`` — including ``request_id`` and ``session_id``
when those are bound by the logging middleware or agent code.
"""
from __future__ import annotations

import logging
import sys

import structlog

from app.config import get_settings

_configured = False


def configure_logging() -> None:
    """Configure structlog and stdlib logging for the application.

    Idempotent: safe to call multiple times (e.g. in tests).

    In ``json`` format mode every record is a single JSON object on stdout.
    In ``text`` format mode records are human-readable coloured output
    (useful when running locally without a log aggregator).
    """
    global _configured
    if _configured:
        return
    _configured = True
    settings = get_settings()
    log_level = getattr(logging, settings.log_level, logging.DEBUG)

    shared_processors: list[structlog.types.Processor] = [
        # Merge any context variables bound via structlog.contextvars
        structlog.contextvars.merge_contextvars,
        # Add log level name
        structlog.stdlib.add_log_level,
        # ISO8601 timestamp
        structlog.processors.TimeStamper(fmt="iso"),
        # Render exception info into the event dict
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.log_format == "json":
        # Production / staging: machine-readable JSON
        structlog.configure(
            processors=[
                *shared_processors,
                structlog.processors.dict_tracebacks,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(log_level),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
            cache_logger_on_first_use=True,
        )
    else:
        # Development: coloured human-readable output
        structlog.configure(
            processors=[
                *shared_processors,
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(log_level),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
            cache_logger_on_first_use=True,
        )

    # Route stdlib ``logging`` calls through structlog so FastAPI / uvicorn /
    # SQLAlchemy logs are captured in the same format.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )
    # Silence noisy libraries at WARNING unless we're in DEBUG mode
    if settings.log_level != "DEBUG":
        for noisy in ("uvicorn.access", "sqlalchemy.engine", "httpx"):
            logging.getLogger(noisy).setLevel(logging.WARNING)
