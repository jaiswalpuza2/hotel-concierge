"""Bikram Sambat (BS) <-> Gregorian (AD) date conversion.

Why a lookup table?
    The Nepali calendar is not algorithmic: the number of days in each BS month
    (29-32) is fixed by the official panchang each year, so conversion needs a
    table of month lengths.

SUPPORTED RANGE
    BS 2080 - 2084  (14 Apr 2023 - 13 Apr 2028).  Dates outside this window raise
    ``DateOutOfRangeError`` so the agent can ask the guest for a Gregorian date
    instead of guessing.

HOW TO EXTEND / VERIFY (important, please read)
    * Each row of ``BS_MONTH_DAYS`` lists the day-count of Baisakh..Chaitra.
    * ``BS_NEW_YEAR_AD`` lists the Gregorian date of 1 Baisakh for every year.
      The unit tests check that the month lengths of every year add up to the
      distance between consecutive New Years, which catches most data-entry
      mistakes. They CANNOT catch a day moved between two months of the same
      year, so before production verify the table against the official Nepal
      Government calendar (e.g. the Nepal Rastriya Panchang Nirnayak Samiti)
      and add more years from the same source.
    * The booking agent always repeats the converted Gregorian date back to the
      guest for confirmation, so a conversion error is visible before money moves.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

# 1 Baisakh of each supported BS year, in Gregorian.
BS_NEW_YEAR_AD: dict[int, date] = {
    2080: date(2023, 4, 14),
    2081: date(2024, 4, 13),
    2082: date(2025, 4, 14),
    2083: date(2026, 4, 14),
    2084: date(2027, 4, 14),
    2085: date(2028, 4, 13),
}

# Days in Baisakh, Jestha, Ashadh, Shrawan, Bhadra, Ashwin, Kartik, Mangsir,
# Poush, Magh, Falgun, Chaitra.
BS_MONTH_DAYS: dict[int, tuple[int, ...]] = {
    2080: (31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 30),
    2081: (31, 31, 32, 32, 31, 30, 30, 30, 29, 30, 30, 30),
    2082: (31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30),
    2083: (31, 31, 32, 31, 31, 30, 30, 30, 29, 30, 30, 30),
    2084: (31, 31, 32, 31, 31, 30, 30, 30, 29, 30, 30, 30),
}

SUPPORTED_BS_YEARS: tuple[int, int] = (min(BS_MONTH_DAYS), max(BS_MONTH_DAYS))

BS_MONTH_NAMES_EN: tuple[str, ...] = (
    "Baisakh", "Jestha", "Ashadh", "Shrawan", "Bhadra", "Ashwin",
    "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra",
)
BS_MONTH_NAMES_NE: tuple[str, ...] = (
    "बैशाख", "जेठ", "असार", "साउन", "भदौ", "असोज",
    "कात्तिक", "मंसिर", "पुष", "माघ", "फागुन", "चैत",
)

# Every spelling we accept from guests (lower-cased Latin or Devanagari).
_MONTH_ALIASES: dict[str, int] = {}
for _num, _names in enumerate(
    [
        ("baisakh", "baishakh", "vaisakh", "vaishakh", "बैशाख", "वैशाख", "बैसाख"),
        ("jestha", "jeth", "jyestha", "jyeshtha", "जेठ", "ज्येष्ठ"),
        ("ashadh", "asar", "asadh", "ashad", "असार", "आषाढ", "अषाढ"),
        ("shrawan", "srawan", "saun", "sawan", "साउन", "श्रावण"),
        ("bhadra", "bhadau", "bhadra", "भदौ", "भाद्र"),
        ("ashwin", "aswin", "asoj", "ashoj", "असोज", "आश्विन"),
        ("kartik", "kattik", "kartick", "कात्तिक", "कार्तिक", "कार्तिक"),
        ("mangsir", "mangshir", "margashirsha", "मंसिर", "मङ्सिर", "मार्ग"),
        ("poush", "push", "pus", "paush", "पुष", "पौष", "पुस"),
        ("magh", "माघ"),
        ("falgun", "fagun", "phalgun", "फागुन", "फाल्गुण", "फाल्गुन"),
        ("chaitra", "chait", "chaita", "चैत", "चैत्र"),
    ],
    start=1,
):
    for _n in _names:
        _MONTH_ALIASES[_n] = _num

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


class DateOutOfRangeError(ValueError):
    """The requested date is outside the supported BS calendar window."""


class InvalidBSDateError(ValueError):
    """The BS year/month/day combination does not exist."""


@dataclass(frozen=True)
class BSDate:
    """A Bikram Sambat calendar date."""

    year: int
    month: int  # 1 = Baisakh ... 12 = Chaitra
    day: int

    def __str__(self) -> str:
        return f"{self.year}-{self.month:02d}-{self.day:02d} BS"

    def month_name(self, lang: str = "en") -> str:
        """Return the month name in English or Devanagari."""
        names = BS_MONTH_NAMES_NE if lang == "ne" else BS_MONTH_NAMES_EN
        return names[self.month - 1]


def days_in_bs_year(year: int) -> int:
    """Total number of days in a BS year."""
    _require_year(year)
    return sum(BS_MONTH_DAYS[year])


def _require_year(year: int) -> None:
    if year not in BS_MONTH_DAYS:
        lo, hi = SUPPORTED_BS_YEARS
        raise DateOutOfRangeError(
            f"BS year {year} is outside the supported range {lo}-{hi}"
        )


def bs_to_gregorian(year: int, month: int, day: int) -> date:
    """Convert a Bikram Sambat date to a Gregorian ``date``.

    Raises:
        DateOutOfRangeError: year outside the supported window.
        InvalidBSDateError: month/day does not exist in that year.
    """
    _require_year(year)
    if not 1 <= month <= 12:
        raise InvalidBSDateError(f"BS month must be 1-12, got {month}")
    month_len = BS_MONTH_DAYS[year][month - 1]
    if not 1 <= day <= month_len:
        raise InvalidBSDateError(
            f"BS {year}-{month:02d} has {month_len} days, got day {day}"
        )
    offset = sum(BS_MONTH_DAYS[year][: month - 1]) + (day - 1)
    return BS_NEW_YEAR_AD[year] + timedelta(days=offset)


def gregorian_to_bs(value: date) -> BSDate:
    """Convert a Gregorian date to Bikram Sambat.

    Raises:
        DateOutOfRangeError: date outside the supported window.
    """
    lo_year, hi_year = SUPPORTED_BS_YEARS
    start = BS_NEW_YEAR_AD[lo_year]
    end = BS_NEW_YEAR_AD[hi_year] + timedelta(days=days_in_bs_year(hi_year) - 1)
    if value < start or value > end:
        raise DateOutOfRangeError(
            f"{value.isoformat()} is outside the supported BS window "
            f"({start.isoformat()} to {end.isoformat()})"
        )
    for year in range(lo_year, hi_year + 1):
        new_year = BS_NEW_YEAR_AD[year]
        if value < new_year + timedelta(days=days_in_bs_year(year)):
            remaining = (value - new_year).days
            for idx, length in enumerate(BS_MONTH_DAYS[year], start=1):
                if remaining < length:
                    return BSDate(year, idx, remaining + 1)
                remaining -= length
    raise DateOutOfRangeError(f"Could not convert {value.isoformat()}")  # pragma: no cover


def parse_month_name(token: str) -> int | None:
    """Return the BS month number (1-12) for a month name, or None."""
    return _MONTH_ALIASES.get(token.strip().lower().rstrip(".,"))


def normalize_digits(text: str) -> str:
    """Convert Devanagari digits (०-९) to ASCII digits."""
    return text.translate(_DEVANAGARI_DIGITS)


def validate_table() -> list[str]:
    """Self-check the calendar data; returns a list of problems (empty = OK)."""
    problems: list[str] = []
    for year, months in BS_MONTH_DAYS.items():
        if len(months) != 12:
            problems.append(f"{year}: expected 12 months, got {len(months)}")
        if not all(29 <= m <= 32 for m in months):
            problems.append(f"{year}: month length outside 29-32")
        nxt = BS_NEW_YEAR_AD.get(year + 1)
        if nxt is None:
            problems.append(f"{year}: missing New Year anchor for {year + 1}")
            continue
        span = (nxt - BS_NEW_YEAR_AD[year]).days
        if span != sum(months):
            problems.append(f"{year}: months sum to {sum(months)} but New Year span is {span}")
    return problems
