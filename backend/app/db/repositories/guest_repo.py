"""GuestRepository — async DB operations for the Guest model."""
from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.guest import Guest
from app.exceptions import NotFoundError

logger = structlog.get_logger(__name__)


class GuestRepository:
    """All async database operations for Guest records.

    Args:
        session: An active SQLAlchemy async session, injected per request.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, guest_id: uuid.UUID) -> Guest:
        """Fetch a guest by primary key.

        Raises:
            NotFoundError: If no guest with that ID exists.
        """
        result = await self._session.execute(
            select(Guest).where(Guest.id == guest_id)
        )
        guest = result.scalar_one_or_none()
        if guest is None:
            raise NotFoundError(
                "Guest not found",
                code="guest_not_found",
                details={"guest_id": str(guest_id)},
            )
        return guest

    async def get_by_phone(self, phone: str) -> Guest | None:
        """Fetch a guest by phone number, returning None if not found."""
        result = await self._session.execute(
            select(Guest).where(Guest.phone == phone)
        )
        return result.scalar_one_or_none()

    async def get_or_create_by_phone(
        self,
        *,
        phone: str,
        name: str,
        email: str | None = None,
        preferred_language: str = "en",
    ) -> tuple[Guest, bool]:
        """Fetch an existing guest by phone, or create a new one.

        Returns:
            A tuple of (guest, created) where ``created`` is True if a new
            guest record was inserted.
        """
        existing = await self.get_by_phone(phone)
        if existing is not None:
            return existing, False

        guest = Guest(
            name=name,
            phone=phone,
            email=email,
            preferred_language=preferred_language,
        )
        self._session.add(guest)
        await self._session.flush()  # assigns the UUID primary key
        logger.info("guest.created", guest_id=str(guest.id), phone=f"***{phone[-4:]}")
        return guest, True
