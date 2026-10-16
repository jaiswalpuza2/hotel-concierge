"""RestaurantRepository -- table reservations with a double-booking guard."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.restaurant import RestaurantTable, TableReservation
from app.exceptions import ConflictError, ValidationError

logger = structlog.get_logger(__name__)

OPEN_TIME = time(7, 0)
LAST_SEATING = time(21, 0)
SLOT_MINUTES = 90  # a party holds a table for 90 minutes


def _minutes(value: time) -> int:
    return value.hour * 60 + value.minute


class RestaurantRepository:
    """Async DB operations for restaurant tables and reservations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def reserve(
        self,
        *,
        reservation_date: date,
        reservation_time: time,
        party_size: int,
        guest_id: Any,
    ) -> tuple[TableReservation, RestaurantTable]:
        """Reserve the smallest free table that fits the party.

        Raises:
            ValidationError: Outside opening hours.
            ConflictError: No suitable table is free at that time.
        """
        if not (OPEN_TIME <= reservation_time <= LAST_SEATING):
            raise ValidationError(
                "The restaurant takes reservations between 07:00 and 21:00",
                code="outside_opening_hours",
                details={"open": "07:00", "last_seating": "21:00"},
            )

        tables_result = await self._session.execute(
            select(RestaurantTable)
            .where(RestaurantTable.capacity >= party_size)
            .order_by(RestaurantTable.capacity, RestaurantTable.id)
            .with_for_update()
        )
        tables = list(tables_result.scalars().all())

        existing_result = await self._session.execute(
            select(TableReservation).where(
                and_(
                    TableReservation.reservation_date == reservation_date,
                    TableReservation.status == "confirmed",
                )
            )
        )
        existing = list(existing_result.scalars().all())

        wanted = _minutes(reservation_time)
        for table in tables:
            clash = any(
                r.table_id == table.id
                and abs(_minutes(r.reservation_time) - wanted) < SLOT_MINUTES
                for r in existing
            )
            if clash:
                continue
            reservation = TableReservation(
                table_id=table.id,
                guest_id=guest_id,
                reservation_date=reservation_date,
                reservation_time=reservation_time,
                party_size=party_size,
                status="confirmed",
            )
            self._session.add(reservation)
            await self._session.flush()
            logger.info(
                "restaurant.reserved",
                table=table.name,
                date=str(reservation_date),
                time=str(reservation_time),
                party=party_size,
            )
            return reservation, table

        raise ConflictError(
            "No table is free at that time for your party size",
            code="no_table_available",
            details={
                "date": str(reservation_date),
                "time": reservation_time.strftime("%H:%M"),
                "party_size": party_size,
            },
        )

    @staticmethod
    def slot_label(start: time) -> str:
        """Human label like '19:30-21:00'."""
        end = (datetime.combine(date.today(), start) + timedelta(minutes=SLOT_MINUTES)).time()
        return f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"
