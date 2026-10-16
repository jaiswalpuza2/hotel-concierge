"""NotificationRepository -- SMS / email delivery log."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.notification import NotificationLog


class NotificationRepository:
    """Async DB operations for NotificationLog records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        booking_id: uuid.UUID,
        channel: str,
        recipient: str,
        message: str,
        success: bool,
        attempts: int,
    ) -> NotificationLog:
        """Persist the outcome of a notification attempt."""
        log = NotificationLog(
            booking_id=booking_id,
            type=channel,
            status="sent" if success else "failed",
            recipient=recipient,
            message=message,
            attempt_count=max(1, attempts),
            sent_at=datetime.now(tz=UTC) if success else None,
        )
        self._session.add(log)
        await self._session.flush()
        return log
