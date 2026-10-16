"""NotificationService -- the Notification Agent's delivery engine.

Sends SMS and email with retries, never raises into the agent, and records every
attempt in ``notification_logs`` for the admin dashboard.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.repositories import NotificationRepository
from app.notifications.base import EmailProvider, SMSProvider
from app.notifications.templates import render_for_effect

logger = structlog.get_logger(__name__)

_ATTEMPTS = 3


class NotificationService:
    """Implements ``NotifierPort`` for the agent graph."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sms: SMSProvider,
        email: EmailProvider,
    ) -> None:
        self._sessions = session_factory
        self._sms = sms
        self._email = email

    async def _with_retry(self, label: str, coro_factory) -> tuple[bool, int]:
        for attempt in range(1, _ATTEMPTS + 1):
            try:
                await coro_factory()
                return True, attempt
            except Exception as exc:
                logger.warning("notification.attempt_failed", channel=label, attempt=attempt, error=str(exc)[:120])
                if attempt < _ATTEMPTS:
                    await asyncio.sleep(0.4 * 2 ** (attempt - 1))
        return False, _ATTEMPTS

    async def _log(self, booking_id: str, channel: str, recipient: str, message: str, ok: bool, attempts: int) -> None:
        try:
            async with self._sessions() as session, session.begin():
                await NotificationRepository(session).record(
                    booking_id=uuid.UUID(booking_id), channel=channel, recipient=recipient,
                    message=message[:2000], success=ok, attempts=attempts,
                )
        except Exception:
            logger.exception("notification.log_failed")

    async def send(self, side_effect: dict[str, Any], reply_style: str) -> bool:
        """Deliver the confirmation for a booking side effect. True if any channel succeeded."""
        style = side_effect.get("language_style") or (
            reply_style if reply_style in ("ne", "ne_roman") else ("ne" if side_effect.get("language") == "ne" else "en")
        )
        rendered = render_for_effect(side_effect, style)
        booking_id = side_effect["booking_id"]
        phone, email = side_effect.get("phone"), side_effect.get("email")
        delivered = False

        if phone:
            ok, attempts = await self._with_retry("sms", lambda: self._sms.send(phone, rendered.sms))
            await self._log(booking_id, "sms", phone, rendered.sms, ok, attempts)
            delivered = delivered or ok
        if email:
            ok, attempts = await self._with_retry(
                "email", lambda: self._email.send(email, rendered.email_subject, rendered.email_body)
            )
            await self._log(booking_id, "email", email, rendered.email_body, ok, attempts)
            delivered = delivered or ok
        logger.info("notification.done", booking=side_effect.get("booking_reference"), delivered=delivered)
        return delivered
