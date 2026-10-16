"""Per-turn event emitter so graph nodes can stream progress to the UI.

Nodes call ``emit({...})``. The chat service installs a callback for the
duration of one turn using a ``ContextVar`` (safe under concurrent requests).
"""
from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

EventCallback = Callable[[dict[str, Any]], Awaitable[None] | None]
_current: ContextVar[EventCallback | None] = ContextVar("concierge_event_callback", default=None)


def set_event_callback(callback: EventCallback | None):
    """Install a callback for the current async context; returns a reset token."""
    return _current.set(callback)


def reset_event_callback(token) -> None:
    """Restore the previous callback."""
    _current.reset(token)


async def emit(event: dict[str, Any]) -> None:
    """Send an event to the active callback (silently ignored when none)."""
    callback = _current.get()
    if callback is None:
        return
    try:
        result = callback(event)
        if inspect.isawaitable(result):
            await result
    except Exception:  # a broken socket must never break the agent
        logger.warning("events.emit_failed", event_type=event.get("type"), exc_info=True)
