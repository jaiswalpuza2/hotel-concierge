"""Bikram Sambat conversion tests."""
from __future__ import annotations

from datetime import date, timedelta

from app.utils.bikram_sambat import (
    BS_NEW_YEAR_AD, DateOutOfRangeError, InvalidBSDateError, bs_to_gregorian, gregorian_to_bs,
    parse_month_name, validate_table,
)


def test_calendar_table_is_internally_consistent():
    assert validate_table() == []


def test_new_year_anchors():
    assert bs_to_gregorian(2083, 1, 1) == date(2026, 4, 14)
    assert bs_to_gregorian(2081, 1, 1) == date(2024, 4, 13)
    assert gregorian_to_bs(date(2025, 4, 14)).year == 2082


def test_round_trip_every_day_in_supported_window():
    day = BS_NEW_YEAR_AD[2080]
    end = BS_NEW_YEAR_AD[2085]
    while day < end:
        bs = gregorian_to_bs(day)
        assert bs_to_gregorian(bs.year, bs.month, bs.day) == day
        day += timedelta(days=1)


def test_consecutive_days_increment_by_one():
    a = bs_to_gregorian(2083, 7, 5)
    assert bs_to_gregorian(2083, 7, 6) - a == timedelta(days=1)
    assert bs_to_gregorian(2083, 8, 1) - bs_to_gregorian(2083, 7, 30) == timedelta(days=1)


def test_out_of_range_and_invalid_dates_raise():
    for call in (lambda: bs_to_gregorian(2050, 1, 1), lambda: gregorian_to_bs(date(2030, 1, 1))):
        try:
            call()
            raise AssertionError("expected DateOutOfRangeError")
        except DateOutOfRangeError:
            pass
    try:
        bs_to_gregorian(2083, 13, 1)
        raise AssertionError("expected InvalidBSDateError")
    except InvalidBSDateError:
        pass
    try:
        bs_to_gregorian(2083, 1, 40)
        raise AssertionError("expected InvalidBSDateError")
    except InvalidBSDateError:
        pass


def test_month_names_in_all_scripts():
    assert parse_month_name("Kartik") == 7
    assert parse_month_name("कात्तिक") == 7
    assert parse_month_name("Poush") == 9
    assert parse_month_name("चैत") == 12
    assert parse_month_name("Tuesday") is None
