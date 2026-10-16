"""NotificationLog ORM model — SMS and email delivery records."""
from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

NotificationType = Literal["sms", "email"]
NotificationStatus = Literal["pending", "sent", "failed"]


class NotificationLog(Base):
    """Records each SMS and email notification attempt.

    A failed delivery is retried once (attempt_count reaches 2).
    Persistent failure is recorded here but does NOT block the guest's
    booking confirmation response.
    """

    __tablename__ = "notification_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=False, index=True
    )
    type: Mapped[NotificationType] = mapped_column(String(20), nullable=False)
    status: Mapped[NotificationStatus] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    # Partially redacted recipient (phone last 4 digits, or email domain only)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sent_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "type IN ('sms','email')", name="ck_notif_type_valid"
        ),
        CheckConstraint(
            "status IN ('pending','sent','failed')", name="ck_notif_status_valid"
        ),
        CheckConstraint("attempt_count >= 1", name="ck_notif_attempt_positive"),
    )

    # Relationships
    booking: Mapped[Booking] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Booking", back_populates="notification_logs"
    )

    def __repr__(self) -> str:
        return (
            f"<NotificationLog type={self.type!r} "
            f"status={self.status!r} booking={str(self.booking_id)[:8]}…>"
        )
