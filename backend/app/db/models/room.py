"""Room and RoomType ORM models."""
from __future__ import annotations

from typing import Literal

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

RoomStatus = Literal["available", "occupied", "maintenance", "reserved"]


class RoomType(Base):
    """A category of hotel room (Standard, Deluxe, Family Suite, Conference Hall).

    ``id`` is a short slug (e.g. ``"deluxe"``) used as FK in other tables
    and as the value passed to tool functions. Human-readable name is stored
    separately so slugs stay stable even if marketing renames a category.
    """

    __tablename__ = "room_types"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    bed_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # Base price in whole NPR (no sub-rupee precision needed for hotel pricing)
    base_price_npr: Mapped[int] = mapped_column(Integer, nullable=False)
    # JSON array of amenities stored as text, e.g. '["AC","WiFi","Hot water"]'
    amenities: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    floor_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        CheckConstraint("capacity > 0", name="ck_room_type_capacity_positive"),
        CheckConstraint("base_price_npr > 0", name="ck_room_type_price_positive"),
    )

    # Relationships
    rooms: Mapped[list[Room]] = relationship("Room", back_populates="room_type_rel")
    seasonal_pricing: Mapped[list[SeasonalPricing]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "SeasonalPricing", back_populates="room_type_rel"
    )

    def __repr__(self) -> str:
        return f"<RoomType {self.id!r} base_price={self.base_price_npr}>"


class Room(Base):
    """A physical hotel room.

    40 rooms total, distributed across the 4 room types. The ``status``
    column is informational; actual availability is determined by querying
    the ``bookings`` table to avoid race conditions.
    """

    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    number: Mapped[str] = mapped_column(String(10), nullable=False, unique=True, index=True)
    floor: Mapped[int] = mapped_column(Integer, nullable=False)
    room_type_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("room_types.id"), nullable=False, index=True
    )
    status: Mapped[RoomStatus] = mapped_column(
        String(20), nullable=False, default="available"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('available','occupied','maintenance','reserved')",
            name="ck_room_status_valid",
        ),
    )

    # Relationships
    room_type_rel: Mapped[RoomType] = relationship("RoomType", back_populates="rooms")
    bookings: Mapped[list[Booking]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Booking", back_populates="room"
    )

    def __repr__(self) -> str:
        return f"<Room #{self.number!r} type={self.room_type_id!r} status={self.status!r}>"
