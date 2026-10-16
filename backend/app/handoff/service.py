"""HandoffService -- ticket lifecycle for human-in-the-loop escalation.

Flow:
1. The graph's ``handoff`` node calls ``escalate`` -> ticket row + conversation status
   ``handed_off`` + alert to the manager (Telegram / Slack).
2. While the conversation is ``handed_off`` the AI stops answering (see ChatService).
3. A manager answers from the dashboard -> ``manager_reply`` stores the message and
   pushes it to the guest's open chat over WebSocket.
4. ``resolve`` closes the ticket, returns the conversation to the AI, and notifies the guest.
"""
from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.messages import msg
from app.agents.ports import HandoffTicketInfo
from app.config import get_settings
from app.db.models.handoff import HandoffTicket
from app.db.repositories import ConversationRepository, HandoffRepository
from app.handoff.providers import AlertProvider, HandoffAlert

logger = structlog.get_logger(__name__)


def ticket_ref(ticket_id: Any) -> str:
    """Short reference shown to guests and managers, e.g. ``HT-3FA85F64``."""
    return "HT-" + str(ticket_id).replace("-", "")[:8].upper()


class GuestPusher:
    """Anything that can push an event to a guest's live chat (WebSocket manager)."""

    async def push(self, session_id: str, event: dict[str, Any]) -> bool:  # pragma: no cover - interface
        raise NotImplementedError


class HandoffService:
    """Implements ``HandoffPort`` and the manager-side operations."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        alerts: AlertProvider,
        pusher: GuestPusher,
    ) -> None:
        self._sessions = session_factory
        self._alerts = alerts
        self._pusher = pusher
        self._dashboard = get_settings().dashboard_url

    async def escalate(
        self,
        *,
        session_id: str,
        conversation_id: str,
        reason: str,
        priority: str,
        summary: str,
        language: str,
        last_guest_message: str,
    ) -> HandoffTicketInfo:
        """Create (or reuse) the open ticket for a conversation and alert the manager."""
        conv_id = uuid.UUID(conversation_id)
        created = False
        async with self._sessions() as session, session.begin():
            existing = (
                await session.execute(
                    select(HandoffTicket).where(
                        HandoffTicket.conversation_id == conv_id, HandoffTicket.status != "resolved"
                    )
                )
            ).scalars().first()
            if existing is not None:
                ticket_id = existing.id
            else:
                ticket = await HandoffRepository(session).create_ticket(
                    conversation_id=conv_id, trigger_reason=reason,
                    conversation_summary=summary or "(no summary)", guest_language=language,
                )
                ticket_id = ticket.id
                created = True
            await ConversationRepository(session).set_status(conv_id, "handed_off")

        ref = ticket_ref(ticket_id)
        if created:
            alert = HandoffAlert(ref, reason, priority, language, summary, last_guest_message, self._dashboard)
            try:
                await self._alerts.send(alert)
            except Exception:
                # The ticket is safe in the database and visible in the dashboard.
                logger.exception("handoff.alert_failed", ref=ref)
        logger.info("handoff.escalated", ref=ref, reason=reason, priority=priority, new=created)
        return HandoffTicketInfo(ticket_id=str(ticket_id), ref=ref)

    async def manager_reply(self, ticket_id: uuid.UUID, manager_id: uuid.UUID, text: str) -> dict[str, Any]:
        """Store the manager's answer and push it to the guest in real time."""
        async with self._sessions() as session, session.begin():
            tickets = HandoffRepository(session)
            ticket = await tickets.reply_and_set_in_progress(ticket_id, text, manager_id)
            conversation = ticket.conversation
            await ConversationRepository(session).add_message(
                conversation.id, role="human_agent", content=text
            )
            session_id = str(conversation.session_id)
            ref = ticket_ref(ticket.id)
        delivered = await self._pusher.push(
            session_id, {"type": "human_message", "text": text, "ticket_ref": ref}
        )
        return {"ticket_ref": ref, "delivered_live": delivered}

    async def resolve(self, ticket_id: uuid.UUID, manager_id: uuid.UUID) -> dict[str, Any]:
        """Close the ticket, hand the conversation back to the AI and tell the guest."""
        async with self._sessions() as session, session.begin():
            ticket = await HandoffRepository(session).resolve(ticket_id, manager_id)
            conversation = ticket.conversation
            await ConversationRepository(session).set_status(conversation.id, "active")
            style = "ne" if ticket.guest_language == "ne" else "en"
            notice = msg("handoff_resolved", style)
            await ConversationRepository(session).add_message(conversation.id, role="assistant", content=notice)
            session_id = str(conversation.session_id)
            ref = ticket_ref(ticket.id)
        delivered = await self._pusher.push(
            session_id, {"type": "handoff_resolved", "text": notice, "ticket_ref": ref}
        )
        return {"ticket_ref": ref, "delivered_live": delivered}
