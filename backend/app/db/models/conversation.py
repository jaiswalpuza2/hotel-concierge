"""Conversation and Message ORM models — chat session history."""
from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

ConversationStatus = Literal["active", "handed_off", "resolved", "abandoned"]
MessageRole = Literal["user", "assistant", "human_agent", "system"]


class Conversation(Base):
    """A chat session between a guest and the AI concierge.

    One session_id maps to one LangGraph checkpoint thread.  The guest_id
    is set as soon as the guest provides their phone number (during booking).
    Before that, the conversation is anonymous.
    """

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True, index=True
    )
    guest_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("guests.id"), nullable=True, index=True
    )
    detected_language: Mapped[str] = mapped_column(
        String(10), nullable=False, default="en"
    )
    started_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_active_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    status: Mapped[ConversationStatus] = mapped_column(
        String(20), nullable=False, default="active"
    )

    # Relationships
    guest: Mapped[Guest | None] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Guest", back_populates="conversations"
    )
    messages: Mapped[list[Message]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )
    handoff_tickets: Mapped[list[HandoffTicket]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "HandoffTicket", back_populates="conversation"
    )

    def __repr__(self) -> str:
        return (
            f"<Conversation session={str(self.session_id)[:8]}… "
            f"status={self.status!r}>"
        )


class Message(Base):
    """A single turn in a conversation."""

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False
    )
    role: Mapped[MessageRole] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # JSON array of {name, arguments, attempt} tool call records
    tool_calls: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # JSON array of {document_name, page, score} citation records
    retrieved_chunks: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_messages_conversation_time", "conversation_id", "created_at"),
    )

    # Relationships
    conversation: Mapped[Conversation] = relationship(
        "Conversation", back_populates="messages"
    )

    def __repr__(self) -> str:
        return f"<Message role={self.role!r} conv={str(self.conversation_id)[:8]}…>"
