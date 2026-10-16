"""Language detection, date extraction and formatting tests."""
from __future__ import annotations

from datetime import date

from app.utils.nepali_text import (
    detect_language, extract_bs_dates, format_date_pretty, format_npr, is_valid_nepal_mobile,
    normalize_phone, resolve_reply_language,
)

TODAY = date(2026, 10, 13)


def test_detects_english():
    assert detect_language("What time is check-out?").style == "en"
    assert detect_language("Do you have a room for tonight?").style == "en"


def test_detects_devanagari():
    info = detect_language("नमस्ते, कोठा खाली छ?")
    assert (info.style, info.language, info.script) == ("ne", "ne", "devanagari")


def test_detects_romanized_nepali():
    for text in ("Dashain ko bela ma family suite kati parcha?", "Mero booking cancel garna paryo",
                 "malai kotha chahiyo"):
        info = detect_language(text)
        assert info.style == "ne_roman" and info.language == "ne" and info.script == "latin", text


def test_lone_greeting_stays_english():
    assert detect_language("Namaste").style == "en"
    assert detect_language("").style == "en"


def test_ui_toggle_overrides_language():
    info = detect_language("hello there")
    assert resolve_reply_language(info, "ne").script == "devanagari"
    assert resolve_reply_language(detect_language("kati parcha"), "en").language == "en"
    assert resolve_reply_language(info, None) == info


def test_extracts_range_in_one_month():
    found = extract_bs_dates("from 5 to 8 Kartik", TODAY)
    assert [m.gregorian for m in found] == [date(2026, 10, 21), date(2026, 10, 24)]


def test_extracts_devanagari_digits_and_month():
    found = extract_bs_dates("५ कात्तिक देखि ८ कात्तिक", TODAY)
    assert [m.bs.day for m in found] == [5, 8] and found[0].bs.month == 7


def test_month_day_order_and_explicit_year():
    assert extract_bs_dates("Kartik 5", TODAY)[0].bs.day == 5
    assert extract_bs_dates("5 Kartik 2083", TODAY)[0].gregorian == date(2026, 10, 21)


def test_past_date_this_year_rolls_to_next_bs_year():
    assert extract_bs_dates("10 Baisakh", TODAY)[0].bs.year == 2084


def test_no_false_positives():
    assert extract_bs_dates("5 pushups and 2 people", TODAY) == []
    assert extract_bs_dates("room for 3 guests", TODAY) == []


def test_money_uses_lakh_grouping():
    assert format_npr(4500) == "NPR 4,500"
    assert format_npr(125000) == "NPR 1,25,000"
    assert format_npr(6000, "ne") == "रू ६,०००"


def test_phone_helpers():
    assert normalize_phone("+977 984-1234567") == "9841234567"
    assert normalize_phone("९८४१२३४५६७") == "9841234567"
    assert is_valid_nepal_mobile("9841234567") and not is_valid_nepal_mobile("12345")


def test_pretty_date_shows_both_calendars():
    label = format_date_pretty(date(2026, 10, 21))
    assert "21 Oct 2026" in label and "5 Kartik 2083 BS" in label
