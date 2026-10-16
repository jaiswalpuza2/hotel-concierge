"""RoomRepository — availability queries and seasonal price calculation."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import structlog
from sqlalchemy import and_, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.booking import Booking
from app.db.models.room import Room, RoomType
from app.db.models.seasonal_pricing import SeasonalPricing
from app.exceptions import NotFoundError

logger = structlog.get_logger(__name__)


class RoomRepository:
    """Async DB operations for rooms and room types."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_room_type(self, room_type_id: str) -> RoomType:
        """Fetch a RoomType by slug ID.

        Raises:
            NotFoundError: If the room type does not exist.
        """
        result = await self._session.execute(
            select(RoomType).where(RoomType.id == room_type_id)
        )
        rt = result.scalar_one_or_none()
        if rt is None:
            raise NotFoundError(
                f"Room type '{room_type_id}' not found",
                code="room_type_not_found",
                details={"room_type_id": room_type_id},
            )
        return rt

    async def find_available_rooms(
        self,
        check_in: date,
        check_out: date,
        guests: int,
        room_type_id: str | None = None,
    ) -> list[Room]:
        """Find rooms available for the given date range and guest count.

        A room is considered available if:
        - Its ``status`` is ``'available'`` (not under maintenance/reserved).
        - Its ``RoomType.capacity >= guests``.
        - It has no overlapping confirmed or pending booking.

        Overlapping means: existing_check_in < check_out AND existing_check_out > check_in.

        Args:
            check_in: Gregorian check-in date (inclusive).
            check_out: Gregorian check-out date (exclusive end).
            guests: Number of guests requiring accommodation.
            room_type_id: Optional filter to a specific room type slug.

        Returns:
            List of available Room objects (with ``room_type_rel`` loaded).
        """
        # Sub-query: IDs of rooms with conflicting active bookings
        overlapping_room_ids = (
            select(Booking.room_id)
            .where(
                and_(
                    Booking.status.in_(["pending", "confirmed"]),
                    Booking.check_in < check_out,
                    Booking.check_out > check_in,
                )
            )
            .scalar_subquery()
        )

        stmt = (
            select(Room)
            .join(Room.room_type_rel)
            .where(
                and_(
                    Room.status == "available",
                    RoomType.capacity >= guests,
                    not_(Room.id.in_(overlapping_room_ids)),
                )
            )
            .options(selectinload(Room.room_type_rel))
            .order_by(RoomType.base_price_npr)
        )

        if room_type_id is not None:
            stmt = stmt.where(Room.room_type_id == room_type_id)

        result = await self._session.execute(stmt)
        rooms = list(result.scalars().all())

        logger.debug(
            "room.availability.checked",
            check_in=str(check_in),
            check_out=str(check_out),
            guests=guests,
            room_type_id=room_type_id,
            available_count=len(rooms),
        )
        return rooms

    async def get_price_with_seasonal(
        self,
        room_type_id: str,
        check_in: date,
        check_out: date,
    ) -> dict:
        """Calculate the total price for a stay, applying seasonal multipliers.

        When multiple seasonal pricing rules overlap the date range, the
        highest multiplier wins (most conservative for the guest — they see
        the peak-season price for the whole stay if any night falls in peak).

        Args:
            room_type_id: Room type slug.
            check_in: Start date.
            check_out: End date.

        Returns:
            Dict with keys: base_price_npr, nights, multiplier, total_npr,
            seasonal_name (or None).

        Raises:
            NotFoundError: If the room type does not exist.
        """
        rt = await self.get_room_type(room_type_id)
        nights = (check_out - check_in).days

        # Find applicable seasonal pricing rules (NULL room_type_id = all types)
        stmt = select(SeasonalPricing).where(
            and_(
                SeasonalPricing.start_date <= check_out,
                SeasonalPricing.end_date >= check_in,
                or_(
                    SeasonalPricing.room_type_id == room_type_id,
                    SeasonalPricing.room_type_id.is_(None),
                ),
            )
        ).order_by(SeasonalPricing.multiplier.desc())

        result = await self._session.execute(stmt)
        rules = list(result.scalars().all())

        # Pick the highest multiplier (most specific wins — room-type-specific
        # rules take precedence over global rules if equal multiplier)
        best_rule: SeasonalPricing | None = None
        best_multiplier = Decimal("1.00")
        for rule in rules:
            if rule.multiplier > best_multiplier:
                best_multiplier = rule.multiplier
                best_rule = rule
            elif rule.multiplier == best_multiplier and best_rule is not None:
                # Prefer room-type-specific over global
                if rule.room_type_id is not None and best_rule.room_type_id is None:
                    best_rule = rule

        total_npr = int(rt.base_price_npr * nights * best_multiplier)

        logger.debug(
            "room.price.calculated",
            room_type_id=room_type_id,
            nights=nights,
            base_price=rt.base_price_npr,
            multiplier=str(best_multiplier),
            total_npr=total_npr,
        )

        return {
            "room_type_id": room_type_id,
            "room_type_name": rt.name,
            "base_price_npr": rt.base_price_npr,
            "nights": nights,
            "multiplier": str(best_multiplier),
            "seasonal_name": (
                best_rule.name
                if best_rule and best_multiplier > Decimal("1.00")
                else None
            ),
            "total_npr": total_npr,
        }
