"""Tool definitions shown to the LLM plus Pydantic models that validate its arguments.

The JSON schemas are hand-written (clean, provider-friendly); the Pydantic models are
the single place where values are validated. ``tests/unit/test_tool_schemas.py``
checks that the two never drift apart.
"""
from __future__ import annotations

import re
from datetime import date, time
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.utils.nepali_text import normalize_phone
from app.utils.timeutil import nepal_today

RoomTypeSlug = Literal["standard", "deluxe", "family_suite", "conference_hall"]
ServiceSlug = Literal[
    "airport_pickup", "bus_park_pickup", "laundry", "koshi_tappu_tour", "dharan_tour"
]
MAX_STAY_NIGHTS = 30
_REF_RE = re.compile(r"^(?:HH-)?([0-9a-fA-F]{6,32}(?:-[0-9a-fA-F-]+)?)$")


def _check_stay(check_in: date, check_out: date) -> None:
    if check_in < nepal_today():
        raise ValueError("check_in is in the past")
    if check_out <= check_in:
        raise ValueError("check_out must be after check_in")
    if (check_out - check_in).days > MAX_STAY_NIGHTS:
        raise ValueError(f"stays longer than {MAX_STAY_NIGHTS} nights need staff help")


class _Phone(BaseModel):
    phone: str

    @field_validator("phone")
    @classmethod
    def _normalise_phone(cls, value: str) -> str:
        digits = normalize_phone(value)
        if len(digits) != 10 or digits[:2] not in {"97", "98"}:
            raise ValueError("phone must be a 10-digit Nepali mobile number starting with 97 or 98")
        return digits


class CheckAvailabilityArgs(BaseModel):
    check_in: date
    check_out: date
    guests: int = Field(ge=1, le=20)
    room_type: RoomTypeSlug | None = None

    @model_validator(mode="after")
    def _dates(self) -> CheckAvailabilityArgs:
        _check_stay(self.check_in, self.check_out)
        return self


class GetRoomPriceArgs(BaseModel):
    room_type: RoomTypeSlug
    check_in: date
    check_out: date
    guests: int = Field(default=1, ge=1, le=20)

    @model_validator(mode="after")
    def _dates(self) -> GetRoomPriceArgs:
        _check_stay(self.check_in, self.check_out)
        return self


class BookRoomArgs(_Phone):
    quote_id: str = Field(min_length=10)
    guest_name: str = Field(min_length=2, max_length=120)
    email: str | None = Field(default=None, max_length=255)
    preferred_language: Literal["en", "ne"] = "en"
    user_confirmed: bool = False

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if "@" not in value or "." not in value.split("@", 1)[1]:
            raise ValueError("email looks invalid")
        return value.strip().lower()


class _BookingRef(_Phone):
    booking_reference: str

    @field_validator("booking_reference")
    @classmethod
    def _ref(cls, value: str) -> str:
        match = _REF_RE.match(value.strip())
        if not match:
            raise ValueError("booking_reference looks invalid (expected like HH-3FA85F64)")
        return match.group(1).lower()


class CancelBookingArgs(_BookingRef):
    user_confirmed: bool = False


class ModifyBookingArgs(_BookingRef):
    new_check_in: date | None = None
    new_check_out: date | None = None
    user_confirmed: bool = False

    @model_validator(mode="after")
    def _need_one(self) -> ModifyBookingArgs:
        if self.new_check_in is None and self.new_check_out is None:
            raise ValueError("provide new_check_in and/or new_check_out")
        return self


class BookingStatusArgs(_BookingRef):
    pass


class ReserveTableArgs(_Phone):
    date: date  # noqa: A003 - mirrors the JSON field name the model sends
    time: time
    party_size: int = Field(ge=1, le=12)
    guest_name: str = Field(min_length=2, max_length=120)

    @model_validator(mode="after")
    def _future(self) -> ReserveTableArgs:
        if self.date < nepal_today():
            raise ValueError("date is in the past")
        return self


class RequestServiceArgs(BaseModel):
    service_type: ServiceSlug
    phone: str | None = None
    booking_reference: str | None = None
    details: str | None = Field(default=None, max_length=500)

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        if not value:
            return None
        digits = normalize_phone(value)
        if len(digits) != 10:
            raise ValueError("phone must be a 10-digit Nepali mobile number")
        return digits

    @field_validator("booking_reference")
    @classmethod
    def _ref(cls, value: str | None) -> str | None:
        if not value:
            return None
        match = _REF_RE.match(value.strip())
        if not match:
            raise ValueError("booking_reference looks invalid")
        return match.group(1).lower()


class SearchKnowledgeArgs(BaseModel):
    query: str = Field(min_length=2, max_length=300)


class NoArgs(BaseModel):
    pass


ARG_MODELS: dict[str, type[BaseModel]] = {
    "check_room_availability": CheckAvailabilityArgs,
    "get_room_price": GetRoomPriceArgs,
    "book_room": BookRoomArgs,
    "cancel_booking": CancelBookingArgs,
    "modify_booking": ModifyBookingArgs,
    "get_booking_status": BookingStatusArgs,
    "reserve_restaurant_table": ReserveTableArgs,
    "request_service": RequestServiceArgs,
    "get_business_hours": NoArgs,
    "search_knowledge_base": SearchKnowledgeArgs,
}

_DATE = {"type": "string", "description": "Gregorian date, ISO format YYYY-MM-DD"}
_ROOM = {
    "type": "string",
    "enum": ["standard", "deluxe", "family_suite", "conference_hall"],
    "description": "Room type slug",
}
_PHONE = {"type": "string", "description": "Guest's 10-digit Nepali mobile number, e.g. 9841234567"}
_REF = {
    "type": "string",
    "description": "Booking reference given at booking time, like HH-3FA85F64",
}


def _fn(name: str, description: str, props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "parameters": {"type": "object", "properties": props, "required": required},
    }


HOTEL_TOOL_SCHEMAS: list[dict[str, Any]] = [
    _fn(
        "check_room_availability",
        "Check which room types are free for a stay and get a price quote_id for each. "
        "Always call this before talking about availability or prices for specific dates.",
        {
            "check_in": _DATE,
            "check_out": {**_DATE, "description": "Gregorian check-out date (the day guests leave)"},
            "guests": {"type": "integer", "minimum": 1, "maximum": 20, "description": "Number of guests"},
            "room_type": _ROOM,
        },
        ["check_in", "check_out", "guests"],
    ),
    _fn(
        "get_room_price",
        "Get the total price for one room type and dates, including festival pricing, with a quote_id.",
        {"room_type": _ROOM, "check_in": _DATE, "check_out": _DATE, "guests": {"type": "integer"}},
        ["room_type", "check_in", "check_out"],
    ),
    _fn(
        "book_room",
        "Create a booking. ONLY call after (1) you showed the guest room type, dates and total price, "
        "(2) the guest explicitly said yes, and (3) you have their name and phone. "
        "Set user_confirmed=true only when the guest explicitly confirmed.",
        {
            "quote_id": {"type": "string", "description": "quote_id returned by the availability/price tool"},
            "guest_name": {"type": "string"},
            "phone": _PHONE,
            "email": {"type": "string", "description": "Optional email for the confirmation"},
            "preferred_language": {"type": "string", "enum": ["en", "ne"]},
            "user_confirmed": {"type": "boolean", "description": "True only if the guest explicitly confirmed"},
        },
        ["quote_id", "guest_name", "phone", "user_confirmed"],
    ),
    _fn(
        "cancel_booking",
        "Cancel a booking. First call with user_confirmed=false to get the refund preview, show it to "
        "the guest, and only call again with user_confirmed=true after they explicitly agree. "
        "Requires the booking reference AND the phone number used when booking.",
        {"booking_reference": _REF, "phone": _PHONE, "user_confirmed": {"type": "boolean"}},
        ["booking_reference", "phone"],
    ),
    _fn(
        "modify_booking",
        "Change the check-in and/or check-out date of an existing booking. First call with "
        "user_confirmed=false to preview the new price, then confirm with the guest.",
        {
            "booking_reference": _REF,
            "phone": _PHONE,
            "new_check_in": _DATE,
            "new_check_out": _DATE,
            "user_confirmed": {"type": "boolean"},
        },
        ["booking_reference", "phone"],
    ),
    _fn(
        "get_booking_status",
        "Look up a booking. Requires the booking reference AND the phone number used when booking.",
        {"booking_reference": _REF, "phone": _PHONE},
        ["booking_reference", "phone"],
    ),
    _fn(
        "reserve_restaurant_table",
        "Reserve a table in the hotel restaurant (open 07:00-21:30).",
        {
            "date": _DATE,
            "time": {"type": "string", "description": "24-hour time HH:MM, e.g. 19:30"},
            "party_size": {"type": "integer", "minimum": 1, "maximum": 12},
            "guest_name": {"type": "string"},
            "phone": _PHONE,
        },
        ["date", "time", "party_size", "guest_name", "phone"],
    ),
    _fn(
        "request_service",
        "Request an extra service (airport/bus-park pickup, laundry, tours). Tell the guest the price first.",
        {
            "service_type": {
                "type": "string",
                "enum": ["airport_pickup", "bus_park_pickup", "laundry", "koshi_tappu_tour", "dharan_tour"],
            },
            "phone": _PHONE,
            "booking_reference": _REF,
            "details": {"type": "string", "description": "Flight/bus number, time, passengers, etc."},
        },
        ["service_type"],
    ),
    _fn(
        "get_business_hours",
        "Get reception, restaurant and check-in/out hours.",
        {},
        [],
    ),
    _fn(
        "search_knowledge_base",
        "Search the hotel's documents (policies, menu, attractions, FAQs). Use for any factual question "
        "about the hotel that is not a live booking/availability lookup.",
        {"query": {"type": "string", "description": "What to look up, in English or Nepali"}},
        ["query"],
    ),
]
