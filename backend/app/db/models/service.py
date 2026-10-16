"""Service and ServiceRequest ORM models."""
from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

ServiceType = Literal[
    "airport_pickup", "bus_park_pickup", "laundry", "koshi_tappu_tour", "dharan_tour"
]
ServiceRequestStatus = Literal["pending", "in_progress", "completed", "cancelled"]


class Service(Base):
    """An additional hotel service that guests can request.

    Services have a fixed NPR price shown to guests before they confirm.
    The ``type`` slug is used by the ``request_service`` tool function.
    """

    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    price_npr: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    __table_args__ = (
        CheckConstraint("price_npr >= 0", name="ck_service_price_non_negative"),
    )

    # Relationships
    service_requests: Mapped[list[ServiceRequest]] = relationship(
        "ServiceRequest", back_populates="service"
    )

    def __repr__(self) -> str:
        return f"<Service {self.type!r} price={self.price_npr}NPR>"


class ServiceRequest(Base):
    """A guest request for an additional service tied to a booking."""

    __tablename__ = "service_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=True, index=True
    )
    service_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("services.id"), nullable=False
    )
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ServiceRequestStatus] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','in_progress','completed','cancelled')",
            name="ck_service_request_status_valid",
        ),
    )

    # Relationships
    booking: Mapped[Booking | None] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Booking", back_populates="service_requests"
    )
    service: Mapped[Service] = relationship("Service", back_populates="service_requests")

    def __repr__(self) -> str:
        return f"<ServiceRequest {str(self.id)[:8]}… status={self.status!r}>"
