"""HandoffRepository — async DB operations for human handoff tickets."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.handoff import HandoffTicket
from app.exceptions import NotFoundError, ValidationError

logger = structlog.get_logger(__name__)


class HandoffRepository:
    """Async DB operations for HandoffTicket records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_ticket(
        self,
        *,
        conversation_id: uuid.UUID,
        trigger_reason: str,
        conversation_summary: str,
        guest_language: str,
        booking_id: uuid.UUID | None = None,
    ) -> HandoffTicket:
        """Create a new open handoff ticket.

        Returns:
            The newly created HandoffTicket.
        """
        ticket = HandoffTicket(
            conversation_id=conversation_id,
            trigger_reason=trigger_reason,
            conversation_summary=conversation_summary,
            guest_language=guest_language,
            booking_id=booking_id,
            status="open",
        )
        self._session.add(ticket)
        await self._session.flush()
        logger.info(
            "handoff.ticket_created",
            ticket_id=str(ticket.id),
            trigger=trigger_reason,
            language=guest_language,
        )
        return ticket

    async def get_by_id(self, ticket_id: uuid.UUID) -> HandoffTicket:
        """Fetch a ticket by primary key.

        Raises:
            NotFoundError: If no ticket with that ID exists.
        """
        result = await self._session.execute(
            select(HandoffTicket)
            .where(HandoffTicket.id == ticket_id)
            .options(selectinload(HandoffTicket.conversation))
        )
        ticket = result.scalar_one_or_none()
        if ticket is None:
            raise NotFoundError(
                "Handoff ticket not found",
                code="ticket_not_found",
                details={"ticket_id": str(ticket_id)},
            )
        return ticket

    async def get_open_tickets(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
    ) -> tuple[list[HandoffTicket], int]:
        """Return tickets ordered by open first, then by creation time desc.

        Returns:
            Tuple of (items, total_count).
        """
        base = select(HandoffTicket).order_by(
            # Open tickets first, then in_progress, then resolved
            case(
                (HandoffTicket.status == "open", 0),
                (HandoffTicket.status == "in_progress", 1),
                else_=2,
            ),
            HandoffTicket.created_at.desc(),
        )
        if status:
            base = base.where(HandoffTicket.status == status)

        count_stmt = select(func.count(HandoffTicket.id))
        if status:
            count_stmt = count_stmt.where(HandoffTicket.status == status)
        total = (await self._session.execute(count_stmt)).scalar_one()

        offset = (page - 1) * page_size
        result = await self._session.execute(
            base.options(selectinload(HandoffTicket.conversation))
            .offset(offset)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    async def reply_and_set_in_progress(
        self,
        ticket_id: uuid.UUID,
        reply: str,
        resolved_by: uuid.UUID,
    ) -> HandoffTicket:
        """Store a manager reply and advance ticket to 'in_progress'.

        Raises:
            NotFoundError: If no ticket with that ID exists.
            ValidationError: If the ticket is already resolved.
        """
        ticket = await self.get_by_id(ticket_id)
        if ticket.status == "resolved":
            raise ValidationError(
                "Cannot reply to a resolved ticket",
                code="ticket_already_resolved",
                details={"ticket_id": str(ticket_id)},
            )
        ticket.manager_reply = reply
        ticket.status = "in_progress"
        ticket.resolved_by = resolved_by
        await self._session.flush()
        logger.info(
            "handoff.ticket_replied",
            ticket_id=str(ticket_id),
            resolved_by=str(resolved_by),
        )
        return ticket

    async def resolve(
        self,
        ticket_id: uuid.UUID,
        resolved_by: uuid.UUID,
    ) -> HandoffTicket:
        """Mark a ticket as resolved.

        Raises:
            NotFoundError: If no ticket with that ID exists.
            ValidationError: If the ticket is already resolved.
        """
        ticket = await self.get_by_id(ticket_id)
        if ticket.status == "resolved":
            raise ValidationError(
                "Ticket is already resolved",
                code="ticket_already_resolved",
                details={"ticket_id": str(ticket_id)},
            )
        ticket.status = "resolved"
        ticket.resolved_by = resolved_by
        ticket.resolved_at = datetime.now(tz=UTC)
        await self._session.flush()
        logger.info(
            "handoff.ticket_resolved",
            ticket_id=str(ticket_id),
            resolved_by=str(resolved_by),
        )
        return ticket
