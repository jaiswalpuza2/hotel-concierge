"""User ORM model — admin and staff accounts for the dashboard."""
from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    """Admin or staff user who can access the management dashboard.

    Guests are not Users — they are stored in the ``Guest`` model.
    Users are created by the system administrator; there is no public
    registration endpoint.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Literal["admin", "staff"]] = mapped_column(
        String(50), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    resolved_tickets: Mapped[list[HandoffTicket]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "HandoffTicket", back_populates="resolved_by_user", foreign_keys="HandoffTicket.resolved_by"
    )

    def __repr__(self) -> str:
        return f"<User {self.email!r} role={self.role!r}>"
