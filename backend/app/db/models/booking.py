"""Booking ORM model."""
from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

BookingStatus = Literal["pending", "confirmed", "cancelled", "completed"]


class Booking(Base):
    """A room booking made by a guest.

    The double-booking guard lives in ``BookingRepository.create_booking``
    which uses ``SELECT … FOR UPDATE`` on the target room before inserting.
    The DB-level ``chk_checkout_after_checkin`` constraint is a safety net.

    Total price is stored in whole NPR and already includes any seasonal
    multiplier applied at booking time by ``get_room_price``.
    """

    __tablename__ = "bookings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    guest_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("guests.id"), nullable=False, index=True
    )
    room_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("rooms.id"), nullable=False
    )
    check_in: Mapped[Date] = mapped_column(Date, nullable=False)
    check_out: Mapped[Date] = mapped_column(Date, nullable=False)
    guests_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[BookingStatus] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    total_price_npr: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("check_out > check_in", name="chk_checkout_after_checkin"),
        CheckConstraint("guests_count > 0", name="ck_booking_guests_positive"),
        CheckConstraint("total_price_npr >= 0", name="ck_booking_price_non_negative"),
        CheckConstraint(
            "status IN ('pending','confirmed','cancelled','completed')",
            name="ck_booking_status_valid",
        ),
        # Partial index: only non-cancelled bookings considered for availability
        Index(
            "idx_bookings_room_dates_active",
            "room_id", "check_in", "check_out",
            postgresql_where="status NOT IN ('cancelled')",
        ),
    )

    # Relationships
    guest: Mapped[Guest] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Guest", back_populates="bookings"
    )
    room: Mapped[Room] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Room", back_populates="bookings"
    )
    service_requests: Mapped[list[ServiceRequest]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "ServiceRequest", back_populates="booking", cascade="all, delete-orphan"
    )
    handoff_tickets: Mapped[list[HandoffTicket]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "HandoffTicket", back_populates="booking"
    )
    notification_logs: Mapped[list[NotificationLog]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "NotificationLog", back_populates="booking", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<Booking {str(self.id)[:8]}… "
            f"check_in={self.check_in} status={self.status!r}>"
        )
