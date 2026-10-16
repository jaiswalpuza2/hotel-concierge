"""In-memory registry of live guest WebSocket connections.

Used to push manager replies and "handoff resolved" notices to the right guest.
NOTE: state lives in this process. To run several API workers, replace ``push`` with a
Redis pub/sub fan-out (the interface is already isolated for that).
"""
from __future__ import annotations

import asyncio
from typing import Any

import structlog
from fastapi import WebSocket

from app.handoff.service import GuestPusher

logger = structlog.get_logger(__name__)


class ConnectionManager(GuestPusher):
    """Tracks sockets per chat session id."""

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        """Register an already-accepted socket."""
        async with self._lock:
            self._connections.setdefault(session_id, set()).add(websocket)

    async def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        """Forget a socket."""
        async with self._lock:
            sockets = self._connections.get(session_id)
            if sockets:
                sockets.discard(websocket)
                if not sockets:
                    self._connections.pop(session_id, None)

    async def push(self, session_id: str, event: dict[str, Any]) -> bool:
        """Send ``event`` to every socket of a session. True if at least one received it."""
        sockets = list(self._connections.get(session_id, ()))
        delivered = False
        for ws in sockets:
            try:
                await ws.send_json(event)
                delivered = True
            except Exception:
                logger.info("ws.push_dropped", session_id=session_id)
                await self.disconnect(session_id, ws)
        return delivered

    @property
    def active_sessions(self) -> int:
        """Number of sessions with at least one open socket."""
        return len(self._connections)
