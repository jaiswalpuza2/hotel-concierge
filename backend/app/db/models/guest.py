"""Guest ORM model — hotel visitors who interact with the concierge."""
from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Guest(Base):
    """A hotel guest or prospective guest.

    Created automatically when a guest provides their phone number during
    booking. Phone number is the primary identity key used for booking
    verification (cancel, modify, status).
    """

    __tablename__ = "guests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    preferred_language: Mapped[Literal["en", "ne"]] = mapped_column(
        String(10), nullable=False, default="en"
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    bookings: Mapped[list[Booking]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Booking", back_populates="guest", cascade="all, delete-orphan"
    )
    table_reservations: Mapped[list[TableReservation]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "TableReservation", back_populates="guest"
    )
    conversations: Mapped[list[Conversation]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Conversation", back_populates="guest"
    )

    def __repr__(self) -> str:
        return f"<Guest {self.name!r} phone={self.phone!r}>"
