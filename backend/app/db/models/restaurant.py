"""RestaurantTable and TableReservation ORM models."""
from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, String, Time
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

TableReservationStatus = Literal["confirmed", "cancelled", "completed"]


class RestaurantTable(Base):
    """A physical table in the hotel restaurant."""

    __tablename__ = "restaurant_tables"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint("capacity > 0", name="ck_table_capacity_positive"),
    )

    # Relationships
    reservations: Mapped[list[TableReservation]] = relationship(
        "TableReservation", back_populates="table"
    )

    def __repr__(self) -> str:
        return f"<RestaurantTable {self.name!r} capacity={self.capacity}>"


class TableReservation(Base):
    """A restaurant table reservation for a specific date and time."""

    __tablename__ = "table_reservations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    table_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("restaurant_tables.id"), nullable=False, index=True
    )
    guest_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("guests.id"), nullable=True, index=True
    )
    reservation_date: Mapped[Date] = mapped_column(Date, nullable=False)
    reservation_time: Mapped[Time] = mapped_column(Time, nullable=False)
    party_size: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[TableReservationStatus] = mapped_column(
        String(20), nullable=False, default="confirmed"
    )

    __table_args__ = (
        CheckConstraint("party_size > 0", name="ck_table_res_party_positive"),
        CheckConstraint(
            "status IN ('confirmed','cancelled','completed')",
            name="ck_table_res_status_valid",
        ),
    )

    # Relationships
    table: Mapped[RestaurantTable] = relationship(
        "RestaurantTable", back_populates="reservations"
    )
    guest: Mapped[Guest | None] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Guest", back_populates="table_reservations"
    )

    def __repr__(self) -> str:
        return (
            f"<TableReservation {str(self.id)[:8]}… "
            f"date={self.reservation_date} time={self.reservation_time}>"
        )
