"""Hotel tool implementations backed by PostgreSQL.

Every tool opens its own short transaction, validates its arguments with Pydantic,
returns structured data (never raises into the agent), and distinguishes:

* business outcomes ("no rooms", "booking not found")  -> ``ok=False, retryable=False``
* infrastructure failures (DB down)                    -> ``ok=False, retryable=True``
"""
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any

import structlog
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db.models.booking import Booking
from app.db.repositories import (
    BookingRepository,
    GuestRepository,
    RestaurantRepository,
    RoomRepository,
    ServiceRepository,
)
from app.exceptions import AppError, ConflictError, NotFoundError
from app.tools.base import ToolContext, ToolResult
from app.tools.quotes import QuoteError, make_quote_token, verify_quote_token
from app.tools.schemas import ARG_MODELS, HOTEL_TOOL_SCHEMAS
from app.utils.nepali_text import format_date_pretty, format_npr

logger = structlog.get_logger(__name__)

SearchFn = Callable[[str], Awaitable[list[dict[str, Any]]]]

BOOKING_REF_PREFIX = "HH-"

BUSINESS_HOURS: dict[str, Any] = {
    "reception": "24 hours, every day",
    "check_in": "from 14:00 (2:00 PM)",
    "check_out": "by 11:00 AM; late check-out until 2:00 PM for NPR 500 (subject to availability)",
    "restaurant": "07:00 to 21:30 (room service until 22:00)",
    "airport_pickup": "24 hours, book at least 2 hours ahead",
    "bus_park_pickup": "06:00 to 22:00, book at least 1 hour ahead",
    "quiet_hours": "22:00 to 07:00",
}


def booking_reference(booking_id: Any) -> str:
    """Short guest-facing reference such as ``HH-3FA85F64``."""
    return BOOKING_REF_PREFIX + str(booking_id).replace("-", "")[:8].upper()


def _err(code: str, message: str, *, retryable: bool = False, **details: Any) -> ToolResult:
    return ToolResult(
        ok=False,
        error={"code": code, "message": message, "details": details},
        retryable=retryable,
    )


def _amenities(raw: str) -> list[str]:
    try:
        value = json.loads(raw)
        return [str(v) for v in value] if isinstance(value, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


class HotelToolExecutor:
    """Runs the hotel tools for the agent graph.

    Args:
        session_factory: Async session factory; each tool call gets its own session.
        search_knowledge: Coroutine used by ``search_knowledge_base``.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        search_knowledge: SearchFn,
    ) -> None:
        self._sessions = session_factory
        self._search = search_knowledge
        self._secret = get_settings().jwt_secret_key.get_secret_value()
        self._handlers: dict[str, Callable[[Any, ToolContext], Awaitable[ToolResult]]] = {
            "check_room_availability": self._check_availability,
            "get_room_price": self._get_price,
            "book_room": self._book_room,
            "cancel_booking": self._cancel_booking,
            "modify_booking": self._modify_booking,
            "get_booking_status": self._booking_status,
            "reserve_restaurant_table": self._reserve_table,
            "request_service": self._request_service,
            "get_business_hours": self._business_hours,
            "search_knowledge_base": self._search_kb,
        }

    @property
    def schemas(self) -> list[dict[str, Any]]:
        """Tool schemas shown to the model."""
        return HOTEL_TOOL_SCHEMAS

    # ------------------------------------------------------------------
    # Dispatcher
    # ------------------------------------------------------------------

    async def execute(self, name: str, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        """Validate arguments, run the tool, and convert every failure to a ToolResult."""
        handler = self._handlers.get(name)
        model_cls: type[BaseModel] | None = ARG_MODELS.get(name)
        if handler is None or model_cls is None:
            return _err("unknown_tool", f"Tool '{name}' does not exist")
        try:
            args = model_cls.model_validate(arguments)
        except PydanticValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(str(p) for p in e['loc']) or 'arguments'}: {e['msg']}" for e in exc.errors()
            )
            return _err("invalid_arguments", f"Invalid arguments: {problems}")

        try:
            result = await handler(args, ctx)
        except QuoteError as exc:
            result = _err(exc.code, exc.message)
        except AppError as exc:
            result = _err(exc.code, exc.message, **exc.details)
        except Exception:
            logger.exception("tool.unexpected_error", tool=name)
            result = _err(
                "tool_internal_error",
                "The booking system had a temporary problem. Please try again.",
                retryable=True,
            )
        logger.info("tool.executed", tool=name, ok=result.ok, retryable=result.retryable)
        return result

    # ------------------------------------------------------------------
    # Availability & pricing
    # ------------------------------------------------------------------

    def _quote_option(
        self, price: dict[str, Any], rt_capacity: int, amenities: list[str], available: int | None,
        check_in: date, check_out: date, guests: int, ctx: ToolContext,
    ) -> dict[str, Any]:
        token = make_quote_token(
            self._secret,
            room_type_id=price["room_type_id"],
            check_in=check_in,
            check_out=check_out,
            guests=guests,
            total_npr=price["total_npr"],
        )
        option: dict[str, Any] = {
            "room_type": price["room_type_id"],
            "name": price["room_type_name"],
            "capacity": rt_capacity,
            "amenities": amenities,
            "nights": price["nights"],
            "price_per_night_npr": price["base_price_npr"],
            "price_multiplier": price["multiplier"],
            "seasonal_note": price["seasonal_name"],
            "total_npr": price["total_npr"],
            "total_formatted": format_npr(price["total_npr"], ctx.language),
            "quote_id": token,
        }
        if available is not None:
            option["rooms_available"] = available
        return option

    async def _check_availability(self, args: Any, ctx: ToolContext) -> ToolResult:
        async with self._sessions() as session:
            repo = RoomRepository(session)
            rooms = await repo.find_available_rooms(
                args.check_in, args.check_out, args.guests, args.room_type
            )
            if args.room_type is None:
                rooms = [r for r in rooms if r.room_type_id != "conference_hall"]
            by_type: dict[str, list[Any]] = {}
            for room in rooms:
                by_type.setdefault(room.room_type_id, []).append(room)

            options: list[dict[str, Any]] = []
            for type_id, type_rooms in by_type.items():
                price = await repo.get_price_with_seasonal(type_id, args.check_in, args.check_out)
                rt = type_rooms[0].room_type_rel
                options.append(
                    self._quote_option(
                        price, rt.capacity, _amenities(rt.amenities), len(type_rooms),
                        args.check_in, args.check_out, args.guests, ctx,
                    )
                )
        options.sort(key=lambda o: o["total_npr"])
        data: dict[str, Any] = {
            "check_in": args.check_in.isoformat(),
            "check_out": args.check_out.isoformat(),
            "check_in_display": format_date_pretty(args.check_in, ctx.language),
            "check_out_display": format_date_pretty(args.check_out, ctx.language),
            "guests": args.guests,
            "options": options,
        }
        if not options:
            data["message"] = (
                "No rooms are free for these dates and guest count. Offer other dates, "
                "a smaller party per room, or a human colleague."
            )
        return ToolResult(ok=True, data=data)

    async def _get_price(self, args: Any, ctx: ToolContext) -> ToolResult:
        async with self._sessions() as session:
            repo = RoomRepository(session)
            rt = await repo.get_room_type(args.room_type)
            price = await repo.get_price_with_seasonal(args.room_type, args.check_in, args.check_out)
            option = self._quote_option(
                price, rt.capacity, _amenities(rt.amenities), None,
                args.check_in, args.check_out, args.guests, ctx,
            )
        option["check_in_display"] = format_date_pretty(args.check_in, ctx.language)
        option["check_out_display"] = format_date_pretty(args.check_out, ctx.language)
        return ToolResult(ok=True, data=option)

    # ------------------------------------------------------------------
    # Booking lifecycle
    # ------------------------------------------------------------------

    async def _book_room(self, args: Any, ctx: ToolContext) -> ToolResult:
        quote = verify_quote_token(self._secret, args.quote_id)
        nights = (quote.check_out - quote.check_in).days
        summary = {
            "room_type": quote.room_type_id,
            "check_in": format_date_pretty(quote.check_in, ctx.language),
            "check_out": format_date_pretty(quote.check_out, ctx.language),
            "nights": nights,
            "guests": quote.guests,
            "total_npr": quote.total_npr,
            "total_formatted": format_npr(quote.total_npr, ctx.language),
        }
        if not args.user_confirmed:
            return _err(
                "confirmation_required",
                "Show the guest this summary and ask for an explicit yes before booking.",
                summary=summary,
            )

        async with self._sessions() as session, session.begin():
            rooms_repo = RoomRepository(session)
            bookings = BookingRepository(session)
            guests_repo = GuestRepository(session)

            current = await rooms_repo.get_price_with_seasonal(
                quote.room_type_id, quote.check_in, quote.check_out
            )
            if current["total_npr"] != quote.total_npr:
                return _err(
                    "price_changed",
                    "The price changed since the quote. Check availability again and re-confirm.",
                    new_total_npr=current["total_npr"],
                )

            candidates = await rooms_repo.find_available_rooms(
                quote.check_in, quote.check_out, quote.guests, quote.room_type_id
            )
            guest, _created = await guests_repo.get_or_create_by_phone(
                phone=args.phone,
                name=args.guest_name,
                email=args.email,
                preferred_language=args.preferred_language,
            )
            booking: Booking | None = None
            chosen_room = None
            for room in candidates:
                try:
                    booking = await bookings.create_booking(
                        guest_id=guest.id,
                        room_id=room.id,
                        check_in=quote.check_in,
                        check_out=quote.check_out,
                        guests_count=quote.guests,
                        total_price_npr=quote.total_npr,
                    )
                    chosen_room = room
                    break
                except ConflictError:
                    continue
            if booking is None or chosen_room is None:
                raise ConflictError(
                    "That room type just became unavailable for these dates",
                    code="room_unavailable",
                    details={"room_type": quote.room_type_id},
                )
            ref = booking_reference(booking.id)
            booking_id = str(booking.id)
            room_number = chosen_room.number

        data = {
            "booking_reference": ref,
            "status": "confirmed",
            "room_type": quote.room_type_id,
            "room_number": room_number,
            **summary,
            "payment": "Pay the full amount at check-in (cash, eSewa, Khalti or bank transfer).",
            "check_in_time": "from 14:00",
        }
        side_effect = {
            "type": "booking_created",
            "booking_id": booking_id,
            "booking_reference": ref,
            "guest_name": args.guest_name,
            "phone": args.phone,
            "email": args.email,
            "language": args.preferred_language if args.preferred_language else ctx.language,
            "summary": summary,
        }
        return ToolResult(ok=True, data=data, side_effect=side_effect)

    async def _find_booking(
        self, session: AsyncSession, reference: str, phone: str
    ) -> Booking:
        return await BookingRepository(session).get_by_reference_and_phone(reference, phone)

    @staticmethod
    def _describe(booking: Booking, ctx: ToolContext) -> dict[str, Any]:
        return {
            "booking_reference": booking_reference(booking.id),
            "status": booking.status,
            "guest_name": booking.guest.name,
            "room_type": booking.room.room_type_rel.name,
            "check_in": format_date_pretty(booking.check_in, ctx.language),
            "check_out": format_date_pretty(booking.check_out, ctx.language),
            "nights": (booking.check_out - booking.check_in).days,
            "guests": booking.guests_count,
            "total_npr": booking.total_price_npr,
            "total_formatted": format_npr(booking.total_price_npr, ctx.language),
        }

    async def _booking_status(self, args: Any, ctx: ToolContext) -> ToolResult:
        async with self._sessions() as session:
            booking = await self._find_booking(session, args.booking_reference, args.phone)
            data = self._describe(booking, ctx)
            data["services"] = [
                {"status": sr.status, "details": sr.details} for sr in booking.service_requests
            ]
        return ToolResult(ok=True, data=data)

    async def _cancel_booking(self, args: Any, ctx: ToolContext) -> ToolResult:
        async with self._sessions() as session, session.begin():
            repo = BookingRepository(session)
            booking = await self._find_booking(session, args.booking_reference, args.phone)
            info = self._describe(booking, ctx)
            policy = repo.refund_policy(booking)
            policy["refund_formatted"] = format_npr(policy["refund_amount_npr"], ctx.language)
            if booking.status in ("cancelled", "completed"):
                return _err(
                    "invalid_booking_status",
                    f"This booking is already {booking.status} and cannot be cancelled.",
                )
            if not args.user_confirmed:
                return _err(
                    "confirmation_required",
                    "Show the refund below and ask the guest to confirm the cancellation.",
                    booking=info,
                    refund=policy,
                )
            result = await repo.cancel_booking(booking)
        data = {**info, "status": "cancelled", "refund": {**policy, **{
            "refund_percentage": result["refund_percentage"],
            "refund_amount_npr": result["refund_amount_npr"],
        }}}
        data["refund"]["refund_formatted"] = format_npr(result["refund_amount_npr"], ctx.language)
        side_effect = {
            "type": "booking_cancelled",
            "booking_id": str(booking.id),
            "booking_reference": booking_reference(booking.id),
            "guest_name": booking.guest.name,
            "phone": booking.guest.phone,
            "email": booking.guest.email,
            "language": booking.guest.preferred_language or ctx.language,
            "refund_formatted": data["refund"]["refund_formatted"],
        }
        return ToolResult(ok=True, data=data, side_effect=side_effect)

    async def _modify_booking(self, args: Any, ctx: ToolContext) -> ToolResult:
        async with self._sessions() as session, session.begin():
            bookings = BookingRepository(session)
            rooms = RoomRepository(session)
            booking = await self._find_booking(session, args.booking_reference, args.phone)
            if booking.status not in ("pending", "confirmed"):
                return _err("invalid_booking_status", f"A {booking.status} booking cannot be changed.")
            new_in = args.new_check_in or booking.check_in
            new_out = args.new_check_out or booking.check_out
            if new_out <= new_in:
                return _err("invalid_dates", "Check-out must be after check-in.")
            if await bookings.has_conflict(
                booking.room_id, new_in, new_out, exclude_booking_id=booking.id
            ):
                return _err(
                    "room_unavailable", "Your room is not free for those new dates.",
                    new_check_in=str(new_in), new_check_out=str(new_out),
                )
            price = await rooms.get_price_with_seasonal(booking.room.room_type_id, new_in, new_out)
            preview = {
                "new_check_in": format_date_pretty(new_in, ctx.language),
                "new_check_out": format_date_pretty(new_out, ctx.language),
                "old_total_npr": booking.total_price_npr,
                "new_total_npr": price["total_npr"],
                "new_total_formatted": format_npr(price["total_npr"], ctx.language),
            }
            if not args.user_confirmed:
                return _err(
                    "confirmation_required",
                    "Show the new dates and price and ask the guest to confirm the change.",
                    preview=preview,
                )
            await bookings.modify_booking(booking, new_check_in=new_in, new_check_out=new_out)
            booking.total_price_npr = price["total_npr"]
            await session.flush()
            data = self._describe(booking, ctx)
        return ToolResult(ok=True, data=data)

    # ------------------------------------------------------------------
    # Restaurant, services, hours, knowledge
    # ------------------------------------------------------------------

    async def _reserve_table(self, args: Any, ctx: ToolContext) -> ToolResult:
        async with self._sessions() as session, session.begin():
            guest, _ = await GuestRepository(session).get_or_create_by_phone(
                phone=args.phone, name=args.guest_name, preferred_language=ctx.language
            )
            reservation, table = await RestaurantRepository(session).reserve(
                reservation_date=args.date,
                reservation_time=args.time,
                party_size=args.party_size,
                guest_id=guest.id,
            )
            data = {
                "reservation_reference": "TB-" + str(reservation.id).replace("-", "")[:8].upper(),
                "table": table.name,
                "date": format_date_pretty(args.date, ctx.language),
                "time": args.time.strftime("%H:%M"),
                "holds_table_for": "90 minutes",
                "party_size": args.party_size,
            }
        return ToolResult(ok=True, data=data)

    async def _request_service(self, args: Any, ctx: ToolContext) -> ToolResult:
        async with self._sessions() as session, session.begin():
            service = await ServiceRepository(session).get_by_type(args.service_type)
            booking_id = None
            if args.booking_reference:
                if not args.phone:
                    return _err("phone_required", "Phone number is needed to attach this to a booking.")
                booking = await self._find_booking(session, args.booking_reference, args.phone)
                booking_id = booking.id
            request = await ServiceRepository(session).create_request(
                service=service, booking_id=booking_id, details=args.details
            )
            data = {
                "request_reference": "SV-" + str(request.id).replace("-", "")[:8].upper(),
                "service": service.name,
                "price_npr": service.price_npr,
                "price_formatted": format_npr(service.price_npr, ctx.language),
                "status": "pending",
                "note": "The front desk will confirm shortly. Payment is collected on service.",
            }
        return ToolResult(ok=True, data=data)

    async def _business_hours(self, args: Any, ctx: ToolContext) -> ToolResult:
        return ToolResult(ok=True, data=dict(BUSINESS_HOURS))

    async def _search_kb(self, args: Any, ctx: ToolContext) -> ToolResult:
        chunks = await self._search(args.query)
        if not chunks:
            return ToolResult(
                ok=True,
                data={"results": [], "message": "Nothing relevant found in the hotel documents."},
            )
        results = [
            {
                "source": c.get("document_name", "document"),
                "section": c.get("section"),
                "text": c["content"],
                "score": round(float(c.get("score", 0.0)), 3),
            }
            for c in chunks
        ]
        citations = [
            {
                "document_name": c.get("document_name", "document"),
                "section": c.get("section"),
                "page": c.get("page_number"),
                "score": round(float(c.get("score", 0.0)), 3),
            }
            for c in chunks
        ]
        return ToolResult(ok=True, data={"results": results}, citations=citations)


__all__ = ["HotelToolExecutor", "booking_reference", "NotFoundError"]
