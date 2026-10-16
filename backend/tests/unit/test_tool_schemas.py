"""Tool schemas must stay in sync with their Pydantic validators (requires pydantic)."""
from __future__ import annotations

from datetime import timedelta

from app.tools.schemas import ARG_MODELS, HOTEL_TOOL_SCHEMAS, BookRoomArgs, CancelBookingArgs, CheckAvailabilityArgs
from app.utils.timeutil import nepal_today


def test_every_schema_has_a_validator_and_matching_fields():
    for schema in HOTEL_TOOL_SCHEMAS:
        model = ARG_MODELS[schema["name"]]
        declared = set(schema["parameters"]["properties"])
        assert declared == set(model.model_fields), schema["name"]
        required = set(schema["parameters"]["required"])
        assert required <= declared


def test_dates_must_be_future_and_ordered():
    today = nepal_today()
    ok = CheckAvailabilityArgs(check_in=today + timedelta(days=3), check_out=today + timedelta(days=5), guests=2)
    assert ok.guests == 2
    for bad in (
        dict(check_in=today - timedelta(days=1), check_out=today + timedelta(days=1), guests=2),
        dict(check_in=today + timedelta(days=3), check_out=today + timedelta(days=3), guests=2),
        dict(check_in=today + timedelta(days=3), check_out=today + timedelta(days=60), guests=2),
        dict(check_in=today + timedelta(days=3), check_out=today + timedelta(days=5), guests=0),
    ):
        try:
            CheckAvailabilityArgs(**bad)
            raise AssertionError(f"should reject {bad}")
        except ValueError:
            pass


def test_phone_is_normalised_and_validated():
    args = BookRoomArgs(quote_id="x" * 12, guest_name="Puja", phone="+977 984-1234567")
    assert args.phone == "9841234567" and args.user_confirmed is False
    try:
        BookRoomArgs(quote_id="x" * 12, guest_name="Puja", phone="12345")
        raise AssertionError("short phone accepted")
    except ValueError:
        pass


def test_booking_reference_accepts_prefix_and_case():
    args = CancelBookingArgs(booking_reference="HH-3FA85F64", phone="9841234567")
    assert args.booking_reference == "3fa85f64"
