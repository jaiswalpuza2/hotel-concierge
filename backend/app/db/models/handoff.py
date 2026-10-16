"""HandoffTicket ORM model — human escalation records."""
from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

HandoffStatus = Literal["open", "in_progress", "resolved"]


class HandoffTicket(Base):
    """A human handoff ticket created when the AI escalates a conversation.

    Lifecycle: open → in_progress (staff opens it) → resolved (staff resolves).
    The ``manager_reply`` is stored here and pushed to the guest's WebSocket
    by the handoff API endpoint.
    """

    __tablename__ = "handoff_tickets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False, index=True
    )
    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=True
    )
    # Machine-readable slug for the trigger reason (see design.md)
    trigger_reason: Mapped[str] = mapped_column(String(100), nullable=False)
    # Plain-text summary of the last N turns for the manager
    conversation_summary: Mapped[str] = mapped_column(Text, nullable=False)
    guest_language: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[HandoffStatus] = mapped_column(
        String(20), nullable=False, default="open"
    )
    manager_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    # FK to users table (the staff member who resolved the ticket)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        # Unresolved tickets first, sorted by creation time
        Index("idx_handoff_status_time", "status", "created_at"),
    )

    # Relationships
    conversation: Mapped[Conversation] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Conversation", back_populates="handoff_tickets"
    )
    booking: Mapped[Booking | None] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Booking", back_populates="handoff_tickets"
    )
    resolved_by_user: Mapped[User | None] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User", back_populates="resolved_tickets", foreign_keys=[resolved_by]
    )

    def __repr__(self) -> str:
        return (
            f"<HandoffTicket {str(self.id)[:8]}… "
            f"trigger={self.trigger_reason!r} status={self.status!r}>"
        )
