"""Staff/admin endpoints: bookings, conversations, handoff inbox, stats, KB indexing."""
from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.base import async_session_factory, get_db_session
from app.db.models.booking import Booking
from app.db.models.document import Document
from app.db.models.handoff import HandoffTicket
from app.db.models.user import User
from app.db.repositories import BookingRepository, ConversationRepository, HandoffRepository
from app.dependencies import get_current_user, get_runtime, require_role
from app.handoff.service import ticket_ref
from app.rag.kb_loader import ingest_folder
from app.tools.hotel_tools import booking_reference
from app.utils.timeutil import nepal_today

router = APIRouter(tags=["admin"])


def _booking_dict(b: Booking) -> dict[str, Any]:
    return {
        "id": str(b.id), "reference": booking_reference(b.id), "status": b.status,
        "guest_name": b.guest.name, "guest_phone": b.guest.phone, "guest_email": b.guest.email,
        "room_number": b.room.number, "room_type": b.room.room_type_rel.name,
        "check_in": b.check_in.isoformat(), "check_out": b.check_out.isoformat(),
        "guests_count": b.guests_count, "total_price_npr": b.total_price_npr,
        "created_at": b.created_at.isoformat(),
    }


def _ticket_dict(t: HandoffTicket) -> dict[str, Any]:
    return {
        "id": str(t.id), "ref": ticket_ref(t.id), "status": t.status, "reason": t.trigger_reason,
        "guest_language": t.guest_language, "summary": t.conversation_summary,
        "manager_reply": t.manager_reply, "conversation_id": str(t.conversation_id),
        "created_at": t.created_at.isoformat(),
        "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None,
    }


# ----------------------------------------------------------------------------- bookings


@router.get("/bookings", summary="List bookings")
async def list_bookings(
    page: int = 1, page_size: int = 20, status: str | None = None,
    from_date: date | None = None, to_date: date | None = None,
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
    _user: User = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Paginated bookings with optional status and date filters."""
    items, total = await BookingRepository(session).list_all(
        page=page, page_size=page_size, status=status, from_date=from_date, to_date=to_date
    )
    return {"items": [_booking_dict(b) for b in items], "total": total, "page": page, "page_size": page_size}


class CancelBody(BaseModel):
    """Staff cancellation request."""

    reason: str | None = Field(default=None, max_length=300)


@router.post("/bookings/{booking_id}/cancel", summary="Cancel a booking on behalf of a guest")
async def cancel_booking(
    booking_id: uuid.UUID, _body: CancelBody,
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
    _user: User = Depends(require_role("admin", "staff")),  # noqa: B008
) -> dict[str, Any]:
    """Cancel a booking and return the refund calculated from the policy."""
    repo = BookingRepository(session)
    booking = await repo.get_by_id(booking_id)
    result = await repo.cancel_booking(booking)
    await session.commit()
    return {"booking_id": str(booking_id), "status": "cancelled", **result}


# ------------------------------------------------------------------------ conversations


@router.get("/conversations", summary="List conversations")
async def list_conversations(
    page: int = 1, page_size: int = 20, status: str | None = None,
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
    _user: User = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Conversations, most recently active first."""
    items, total = await ConversationRepository(session).list_all(page=page, page_size=page_size, status=status)
    return {
        "items": [
            {"id": str(c.id), "session_id": str(c.session_id), "status": c.status,
             "language": c.detected_language, "last_active_at": c.last_active_at.isoformat()}
            for c in items
        ],
        "total": total, "page": page, "page_size": page_size,
    }


@router.get("/conversations/{conversation_id}", summary="Conversation with all messages")
async def get_conversation(
    conversation_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
    _user: User = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Full transcript including tool calls and cited sources (for staff review)."""
    conversation = await ConversationRepository(session).get_by_id(conversation_id)
    return {
        "id": str(conversation.id), "session_id": str(conversation.session_id), "status": conversation.status,
        "language": conversation.detected_language,
        "messages": [
            {"role": m.role, "content": m.content, "intent": m.intent, "confidence": m.confidence,
             "tool_calls": m.tool_calls, "sources": m.retrieved_chunks, "created_at": m.created_at.isoformat()}
            for m in sorted(conversation.messages, key=lambda x: x.created_at)
        ],
    }


# ---------------------------------------------------------------------------- handoffs


@router.get("/handoffs", summary="Handoff inbox")
async def list_handoffs(
    page: int = 1, page_size: int = 20, status: str | None = None,
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
    _user: User = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Open tickets first, then in-progress, then resolved."""
    repo = HandoffRepository(session)
    items, total = await repo.get_open_tickets(page=page, page_size=page_size, status=status)
    return {"items": [_ticket_dict(t) for t in items], "total": total, "page": page, "page_size": page_size}


@router.get("/handoffs/{ticket_id}", summary="One ticket with the conversation transcript")
async def get_handoff(
    ticket_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
    _user: User = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Ticket details plus the full conversation so the manager has context."""
    ticket = await HandoffRepository(session).get_by_id(ticket_id)
    conversation = await ConversationRepository(session).get_by_id(ticket.conversation_id)
    return {
        **_ticket_dict(ticket),
        "messages": [
            {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()}
            for m in sorted(conversation.messages, key=lambda x: x.created_at)
        ],
    }


class ReplyBody(BaseModel):
    """Manager's answer to the guest."""

    text: str = Field(min_length=1, max_length=2000)


@router.post("/handoffs/{ticket_id}/reply", summary="Reply to the guest as a human")
async def reply_handoff(
    ticket_id: uuid.UUID, body: ReplyBody, runtime=Depends(get_runtime),  # noqa: B008
    user: User = Depends(require_role("admin", "staff")),  # noqa: B008
) -> dict[str, Any]:
    """Store the reply and push it live into the guest's chat."""
    return await runtime.handoff.manager_reply(ticket_id, user.id, body.text.strip())


@router.post("/handoffs/{ticket_id}/resolve", summary="Close the ticket and give the chat back to the AI")
async def resolve_handoff(
    ticket_id: uuid.UUID, runtime=Depends(get_runtime),  # noqa: B008
    user: User = Depends(require_role("admin", "staff")),  # noqa: B008
) -> dict[str, Any]:
    """Resolve the ticket; the guest is notified and the AI resumes."""
    return await runtime.handoff.resolve(ticket_id, user.id)


# ------------------------------------------------------------------------------ stats


@router.get("/stats", summary="Dashboard summary numbers")
async def stats(
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
    _user: User = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Counts shown on the admin home page."""
    today = nepal_today()

    async def count(stmt) -> int:  # type: ignore[no-untyped-def]
        return int((await session.execute(stmt)).scalar_one())

    return {
        "open_handoffs": await count(select(func.count(HandoffTicket.id)).where(HandoffTicket.status == "open")),
        "in_progress_handoffs": await count(
            select(func.count(HandoffTicket.id)).where(HandoffTicket.status == "in_progress")
        ),
        "upcoming_bookings": await count(
            select(func.count(Booking.id)).where(Booking.status == "confirmed", Booking.check_in >= today)
        ),
        "arrivals_today": await count(
            select(func.count(Booking.id)).where(Booking.status == "confirmed", Booking.check_in == today)
        ),
        "documents_indexed": await count(select(func.count(Document.id)).where(Document.status == "indexed")),
        "documents_failed": await count(select(func.count(Document.id)).where(Document.status == "failed")),
    }


# ------------------------------------------------------------------------ KB indexing


@router.post("/documents/ingest-sample-kb", status_code=202, summary="Index the bundled sample knowledge base")
async def ingest_sample_kb(
    background: BackgroundTasks,
    _user: User = Depends(require_role("admin")),  # noqa: B008
) -> dict[str, str]:
    """Queue indexing of ``knowledge_base/en`` and ``knowledge_base/ne`` (idempotent)."""
    root = Path(get_settings().knowledge_base_path)
    background.add_task(ingest_folder, async_session_factory, root)
    return {"status": "queued", "path": str(root)}
