"""BookingRepository — async DB operations for bookings.

The double-booking guard uses SELECT … FOR UPDATE on the target room row
inside an explicit transaction so concurrent requests serialise correctly.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Any

import structlog
from sqlalchemy import String, and_, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.booking import Booking
from app.db.models.guest import Guest
from app.db.models.room import Room
from app.exceptions import ConflictError, NotFoundError, ValidationError
from app.utils.timeutil import NEPAL_TZ, nepal_now

logger = structlog.get_logger(__name__)


class BookingRepository:
    """Async DB operations for Booking records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_by_id(self, booking_id: uuid.UUID) -> Booking:
        """Fetch a booking by primary key with guest and room pre-loaded.

        Raises:
            NotFoundError: If no booking with that ID exists.
        """
        result = await self._session.execute(
            select(Booking)
            .where(Booking.id == booking_id)
            .options(
                selectinload(Booking.guest),
                selectinload(Booking.room).selectinload(Room.room_type_rel),
                selectinload(Booking.service_requests),
            )
        )
        booking = result.scalar_one_or_none()
        if booking is None:
            raise NotFoundError(
                "Booking not found",
                code="booking_not_found",
                details={"booking_id": str(booking_id)},
            )
        return booking

    async def get_by_id_and_phone(
        self, booking_id: uuid.UUID, phone: str
    ) -> Booking:
        """Fetch a booking only if the supplied phone matches the guest.

        Used by cancel / modify / status to verify caller identity.

        Raises:
            NotFoundError: Booking not found (deliberately vague to prevent
                enumeration — we don't reveal whether booking exists but
                phone is wrong).
        """
        result = await self._session.execute(
            select(Booking)
            .join(Booking.guest)
            .where(
                and_(
                    Booking.id == booking_id,
                    Guest.phone == phone,
                )
            )
            .options(
                selectinload(Booking.guest),
                selectinload(Booking.room).selectinload(Room.room_type_rel),
                selectinload(Booking.service_requests),
            )
        )
        booking = result.scalar_one_or_none()
        if booking is None:
            raise NotFoundError(
                "Booking not found or phone number does not match",
                code="booking_not_found",
                details={"booking_id": str(booking_id)},
            )
        return booking

    async def get_by_reference_and_phone(self, reference: str, phone: str) -> Booking:
        """Find a booking by its short reference (first hex chars of the UUID) and phone.

        Guests see ``HH-3FA85F64``; the caller strips the prefix and lower-cases it.
        The phone must match, so a guessed reference alone reveals nothing.

        Raises:
            NotFoundError: No booking matches both reference and phone.
        """
        ref = reference.strip().lower().replace("hh-", "", 1)
        if len(ref) < 6 or not all(c in "0123456789abcdef-" for c in ref):
            raise NotFoundError(
                "Booking not found or phone number does not match",
                code="booking_not_found",
            )
        result = await self._session.execute(
            select(Booking)
            .join(Booking.guest)
            .where(and_(cast(Booking.id, String).like(f"{ref}%"), Guest.phone == phone))
            .options(
                selectinload(Booking.guest),
                selectinload(Booking.room).selectinload(Room.room_type_rel),
                selectinload(Booking.service_requests),
            )
            .limit(2)
        )
        matches = list(result.scalars().all())
        if len(matches) != 1:
            raise NotFoundError(
                "Booking not found or phone number does not match",
                code="booking_not_found",
            )
        return matches[0]

    async def has_conflict(
        self,
        room_id: int,
        check_in: date,
        check_out: date,
        *,
        exclude_booking_id: uuid.UUID | None = None,
    ) -> bool:
        """True if an active booking overlaps the range for this room."""
        conditions = [
            Booking.room_id == room_id,
            Booking.status.in_(["pending", "confirmed"]),
            Booking.check_in < check_out,
            Booking.check_out > check_in,
        ]
        if exclude_booking_id is not None:
            conditions.append(Booking.id != exclude_booking_id)
        result = await self._session.execute(select(Booking.id).where(and_(*conditions)).limit(1))
        return result.scalar_one_or_none() is not None

    @staticmethod
    def refund_policy(booking: Booking, now: datetime | None = None) -> dict[str, Any]:
        """Compute the refund a cancellation would earn right now (no DB writes).

        Policy (hotel_policies.md): >48h before check-in 100%, 24-48h 50%, <24h 0%.
        Check-in time is 14:00 Nepal time.
        """
        current = now or nepal_now()
        check_in_dt = datetime.combine(booking.check_in, time(14, 0), tzinfo=NEPAL_TZ)
        hours = (check_in_dt - current).total_seconds() / 3600
        if hours > 48:
            pct = 100
        elif hours > 24:
            pct = 50
        else:
            pct = 0
        return {
            "refund_percentage": pct,
            "refund_amount_npr": int(booking.total_price_npr * pct / 100),
            "original_total_npr": booking.total_price_npr,
            "hours_until_check_in": round(hours, 1),
        }

    async def list_all(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        room_type_id: str | None = None,
    ) -> tuple[list[Booking], int]:
        """Return a paginated list of bookings with optional filters.

        Returns:
            Tuple of (items, total_count).
        """
        base = (
            select(Booking)
            .join(Booking.room)
            .join(Room.room_type_rel)
            .options(
                selectinload(Booking.guest),
                selectinload(Booking.room).selectinload(Room.room_type_rel),
            )
            .order_by(Booking.created_at.desc())
        )

        conditions = []
        if status:
            conditions.append(Booking.status == status)
        if from_date:
            conditions.append(Booking.check_in >= from_date)
        if to_date:
            conditions.append(Booking.check_out <= to_date)
        if room_type_id:
            conditions.append(Room.room_type_id == room_type_id)
        if conditions:
            base = base.where(and_(*conditions))

        count_stmt = select(func.count(Booking.id)).join(Booking.room).join(Room.room_type_rel)
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await self._session.execute(count_stmt)).scalar_one()

        offset = (page - 1) * page_size
        result = await self._session.execute(
            base.offset(offset).limit(page_size)
        )
        return list(result.scalars().all()), total

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def create_booking(
        self,
        *,
        guest_id: uuid.UUID,
        room_id: int,
        check_in: date,
        check_out: date,
        guests_count: int,
        total_price_npr: int,
    ) -> Booking:
        """Insert a new booking with a double-booking guard.

        Uses ``SELECT … FOR UPDATE`` on the target room row then checks for
        overlapping active bookings before inserting. The caller must be
        inside an active transaction (``async with session.begin()``).

        Raises:
            ConflictError: If the room is no longer available (race condition).
            ValidationError: If check_out is not after check_in.
        """
        if check_out <= check_in:
            raise ValidationError(
                "Check-out date must be after check-in date",
                code="invalid_dates",
                details={"check_in": str(check_in), "check_out": str(check_out)},
            )

        # Lock the room row to prevent concurrent bookings
        room_result = await self._session.execute(
            select(Room).where(Room.id == room_id).with_for_update()
        )
        room = room_result.scalar_one_or_none()
        if room is None:
            raise NotFoundError(
                "Room not found",
                code="room_not_found",
                details={"room_id": room_id},
            )

        # Check for overlapping active bookings
        conflict_result = await self._session.execute(
            select(Booking.id).where(
                and_(
                    Booking.room_id == room_id,
                    Booking.status.in_(["pending", "confirmed"]),
                    Booking.check_in < check_out,
                    Booking.check_out > check_in,
                )
            )
        )
        if conflict_result.scalar_one_or_none() is not None:
            raise ConflictError(
                "This room is no longer available for the selected dates",
                code="room_unavailable",
                details={
                    "room_id": room_id,
                    "check_in": str(check_in),
                    "check_out": str(check_out),
                },
            )

        booking = Booking(
            guest_id=guest_id,
            room_id=room_id,
            check_in=check_in,
            check_out=check_out,
            guests_count=guests_count,
            status="confirmed",
            total_price_npr=total_price_npr,
        )
        self._session.add(booking)
        await self._session.flush()

        logger.info(
            "booking.created",
            booking_id=str(booking.id),
            room_id=room_id,
            check_in=str(check_in),
            check_out=str(check_out),
            total_npr=total_price_npr,
        )
        return booking

    async def cancel_booking(self, booking: Booking) -> dict[str, Any]:
        """Cancel a booking and apply the cancellation policy.

        Policy:
            >48 hours before check-in  → full refund (100%)
            24–48 hours before check-in → 50% refund
            <24 hours before check-in  → no refund (0%)

        Args:
            booking: The Booking instance (already verified as belonging to
                the caller via ``get_by_id_and_phone``).

        Returns:
            Dict with cancellation details including refund_amount_npr.

        Raises:
            ValidationError: If the booking is already cancelled or completed.
        """
        if booking.status in ("cancelled", "completed"):
            raise ValidationError(
                f"Booking cannot be cancelled (current status: {booking.status})",
                code="invalid_booking_status",
                details={"booking_id": str(booking.id), "status": booking.status},
            )

        policy = self.refund_policy(booking)
        refund_pct = policy["refund_percentage"]
        refund_npr = policy["refund_amount_npr"]

        booking.status = "cancelled"
        await self._session.flush()

        logger.info(
            "booking.cancelled",
            booking_id=str(booking.id),
            refund_pct=refund_pct,
            refund_npr=refund_npr,
        )
        return {
            "booking_id": str(booking.id),
            "status": "cancelled",
            "refund_percentage": refund_pct,
            "refund_amount_npr": refund_npr,
            "original_total_npr": booking.total_price_npr,
        }

    async def modify_booking(
        self,
        booking: Booking,
        *,
        new_check_in: date | None = None,
        new_check_out: date | None = None,
    ) -> Booking:
        """Change the check-in or check-out dates of an existing booking.

        Uses the same double-booking guard as ``create_booking``.

        Raises:
            ValidationError: If no new dates provided or dates are invalid.
            ConflictError: If the new dates conflict with another booking.
        """
        if new_check_in is None and new_check_out is None:
            raise ValidationError(
                "Provide at least one of new_check_in or new_check_out",
                code="no_new_dates",
            )

        ci = new_check_in or booking.check_in
        co = new_check_out or booking.check_out

        if co <= ci:
            raise ValidationError(
                "Check-out must be after check-in",
                code="invalid_dates",
                details={"new_check_in": str(ci), "new_check_out": str(co)},
            )

        # Check for conflicts, excluding this booking itself
        conflict_result = await self._session.execute(
            select(Booking.id).where(
                and_(
                    Booking.room_id == booking.room_id,
                    Booking.id != booking.id,
                    Booking.status.in_(["pending", "confirmed"]),
                    Booking.check_in < co,
                    Booking.check_out > ci,
                )
            )
        )
        if conflict_result.scalar_one_or_none() is not None:
            raise ConflictError(
                "The new dates conflict with an existing booking",
                code="room_unavailable",
                details={"new_check_in": str(ci), "new_check_out": str(co)},
            )

        booking.check_in = ci
        booking.check_out = co
        await self._session.flush()

        logger.info(
            "booking.modified",
            booking_id=str(booking.id),
            new_check_in=str(ci),
            new_check_out=str(co),
        )
        return booking
