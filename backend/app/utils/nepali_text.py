"""Nepali / English text helpers: language detection, BS date extraction, NPR formatting.

Pure Python (no third-party imports) so it is trivially unit-testable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.utils.bikram_sambat import (
    BSDate,
    DateOutOfRangeError,
    InvalidBSDateError,
    bs_to_gregorian,
    gregorian_to_bs,
    normalize_digits,
    parse_month_name,
)

InputStyle = Literal["en", "ne", "ne_roman"]
Language = Literal["en", "ne"]
Script = Literal["latin", "devanagari"]

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
_LATIN_LETTER_RE = re.compile(r"[A-Za-z]")
_TOKEN_RE = re.compile(r"[a-zA-Z']+")

# Romanized-Nepali markers. "strong" words are almost never English.
_STRONG_ROMAN = frozenset(
    {
        "kati", "parcha", "parchha", "paryo", "garna", "garnu", "garne", "garera",
        "malai", "mero", "hamro", "tapai", "tapaiko", "hajur", "chha", "chhan", "chhu",
        "chaiyo", "chahiyo", "chahincha", "chaincha", "kaha", "kahile", "kasari", "kasto",
        "huncha", "hunchha", "hudaina", "bhayo", "bhane", "bhanera", "dinus", "dinuhos",
        "pathaidinus", "pathaunu", "kripaya", "bela", "kotha", "bhaat", "khaja", "ghar",
        "ramro", "thikai", "hoina", "xa", "cha", "ho", "raixa", "rahecha", "sakchu",
        "sakchhu", "sakincha", "lagcha", "lagchha", "kina", "yahaa", "yaha", "tyaha",
        "gunaso", "radda", "paisa", "rupaiya", "rupaiyan", "bujhina", "bujhe",
    }
)
_WEAK_ROMAN = frozenset(
    {"ko", "ka", "ki", "ma", "ra", "pani", "ta", "nai", "namaste", "dhanyabad", "dhanyawad", "aja", "bholi"}
)
# Ambiguous strong markers that only count when other markers are present.
_AMBIGUOUS = frozenset({"ho", "cha", "ghar"})

_NE_MONTH_RE = (
    r"(?:(?:baisakh|baishakh|vaisakh|vaishakh|jestha|jeth|jyestha|ashadh|asar|asadh|ashad|"
    r"shrawan|srawan|saun|sawan|bhadra|bhadau|ashwin|aswin|asoj|ashoj|kartik|kattik|kartick|"
    r"mangsir|mangshir|poush|push|pus|paush|magh|falgun|fagun|phalgun|chaitra|chait|chaita)"
    r"(?![A-Za-z])|[\u0900-\u097F]+)"
)
_SEP = r"(?:to|till|until|and|-|–|—|देखि|dekhi|सम्म|samma)"

# "5 to 8 Kartik" / "5-8 Kartik" / "५ देखि ८ कार्तिक"
_RANGE_RE = re.compile(
    rf"(?<!\d)(\d{{1,2}})(?:st|nd|rd|th)?\s*{_SEP}\s*(\d{{1,2}})(?:st|nd|rd|th)?\s+({_NE_MONTH_RE})"
    r"(?:\s*,?\s*(20\d{2}))?",
    re.IGNORECASE,
)
# "5 Kartik [2083]" / "5th of Kartik"
_DAY_MONTH_RE = re.compile(
    rf"(?<!\d)(\d{{1,2}})(?:st|nd|rd|th)?\s*(?:of\s+)?({_NE_MONTH_RE})(?:\s*,?\s*(20\d{{2}}))?",
    re.IGNORECASE,
)
# "Kartik 5 [2083]"
_MONTH_DAY_RE = re.compile(
    rf"\b({_NE_MONTH_RE})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?!\d)(?:\s*,?\s*(20\d{{2}}))?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class LangInfo:
    """Result of language detection for one user message."""

    style: InputStyle  # what the user typed
    language: Language  # language to reply in
    script: Script  # script to reply in


@dataclass(frozen=True)
class DateMention:
    """A Bikram Sambat date found in free text, with its Gregorian equivalent."""

    raw: str
    bs: BSDate
    gregorian: date


def detect_language(text: str) -> LangInfo:
    """Classify text as English, Devanagari Nepali, or Romanized Nepali."""
    stripped = text.strip()
    if not stripped:
        return LangInfo("en", "en", "latin")

    dev = len(_DEVANAGARI_RE.findall(stripped))
    lat = len(_LATIN_LETTER_RE.findall(stripped))
    total_letters = dev + lat
    if total_letters and dev / total_letters >= 0.3:
        return LangInfo("ne", "ne", "devanagari")

    tokens = [t.lower() for t in _TOKEN_RE.findall(stripped)]
    if not tokens:
        return LangInfo("en", "en", "latin")

    strong = [t for t in tokens if t in _STRONG_ROMAN and t not in _AMBIGUOUS]
    ambiguous = [t for t in tokens if t in _AMBIGUOUS]
    weak = [t for t in tokens if t in _WEAK_ROMAN]
    score = len(strong) + 0.5 * len(weak) + (0.5 * len(ambiguous) if strong else 0.0)
    if score >= 2 or (score >= 1 and len(tokens) <= 4 and strong):
        return LangInfo("ne_roman", "ne", "latin")
    return LangInfo("en", "en", "latin")


def resolve_reply_language(info: LangInfo, ui_language: str | None) -> LangInfo:
    """Combine detected style with the UI toggle.

    The toggle wins on language; the script follows what the user actually typed
    (Romanized input -> Romanized reply) unless the toggle is Nepali and the user
    typed Latin letters, in which case we answer in Devanagari.
    """
    if ui_language == "en" and info.style == "en":
        return info
    if ui_language == "ne":
        if info.style == "ne_roman":
            return LangInfo("ne_roman", "ne", "latin")
        return LangInfo("ne" if info.style == "ne" else "en", "ne", "devanagari")
    if ui_language == "en" and info.style != "en":
        # User explicitly chose English in the UI; keep detection for style but reply in English.
        return LangInfo(info.style, "en", "latin")
    return info


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------


def _default_year(month: int, day: int, today: date) -> int | None:
    """Pick the BS year (today's, or next) that makes the date not in the past."""
    try:
        current = gregorian_to_bs(today)
    except DateOutOfRangeError:
        return None
    year = current.year
    try:
        if bs_to_gregorian(year, month, min(day, 29)) < today and (month, day) < (
            current.month,
            current.day,
        ):
            year += 1
    except (DateOutOfRangeError, InvalidBSDateError):
        return None
    return year


def _build(day_s: str, month_s: str, year_s: str | None, today: date) -> DateMention | None:
    month = parse_month_name(month_s)
    if month is None:
        return None
    day = int(normalize_digits(day_s))
    year = int(year_s) if year_s else _default_year(month, day, today)
    if year is None:
        return None
    try:
        greg = bs_to_gregorian(year, month, day)
    except (DateOutOfRangeError, InvalidBSDateError):
        return None
    return DateMention(raw=f"{day_s} {month_s}", bs=BSDate(year, month, day), gregorian=greg)


def extract_bs_dates(text: str, today: date | None = None) -> list[DateMention]:
    """Find Bikram Sambat dates such as '5 Kartik', 'कात्तिक ५', or '5 to 8 Kartik'."""
    today = today or date.today()
    normalized = normalize_digits(text)
    found: list[DateMention] = []
    consumed: list[tuple[int, int]] = []

    def overlaps(span: tuple[int, int]) -> bool:
        return any(span[0] < e and s < span[1] for s, e in consumed)

    for match in _RANGE_RE.finditer(normalized):
        d1, d2, month_s, year_s = match.groups()
        first = _build(d1, month_s, year_s, today)
        second = _build(d2, month_s, year_s, today)
        if first and second:
            found.extend([first, second])
            consumed.append(match.span())

    for regex, order in ((_DAY_MONTH_RE, "dm"), (_MONTH_DAY_RE, "md")):
        for match in regex.finditer(normalized):
            if overlaps(match.span()):
                continue
            g = match.groups()
            day_s, month_s, year_s = (g[0], g[1], g[2]) if order == "dm" else (g[1], g[0], g[2])
            mention = _build(day_s, month_s, year_s, today)
            if mention:
                found.append(mention)
                consumed.append(match.span())

    found.sort(key=lambda m: m.gregorian)
    return found


def describe_date_mentions(mentions: list[DateMention]) -> str:
    """Human/LLM readable note about converted dates (empty string if none)."""
    if not mentions:
        return ""
    parts = [
        f"'{m.raw}' = {m.gregorian.isoformat()} ({m.bs.year}-{m.bs.month:02d}-{m.bs.day:02d} BS)"
        for m in mentions
    ]
    return "Bikram Sambat dates found: " + "; ".join(parts)


# ---------------------------------------------------------------------------
# Phone numbers, money
# ---------------------------------------------------------------------------


def normalize_phone(raw: str) -> str:
    """Normalize a Nepali phone number to its national digits (e.g. 9841234567)."""
    digits = re.sub(r"\D", "", normalize_digits(raw))
    if digits.startswith("00977"):
        digits = digits[5:]
    elif digits.startswith("977") and len(digits) > 10:
        digits = digits[3:]
    return digits


def is_valid_nepal_mobile(phone: str) -> bool:
    """Nepali mobile numbers are 10 digits starting with 97 or 98."""
    digits = normalize_phone(phone)
    return len(digits) == 10 and digits[:2] in {"97", "98"}


def _indian_grouping(n: int) -> str:
    s = str(abs(n))
    if len(s) <= 3:
        out = s
    else:
        head, tail = s[:-3], s[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        out = ",".join([*groups, tail])
    return ("-" if n < 0 else "") + out


def to_devanagari_digits(text: str) -> str:
    """Convert ASCII digits to Devanagari digits."""
    return text.translate(str.maketrans("0123456789", "०१२३४५६७८९"))


def format_npr(amount: int, lang: str = "en") -> str:
    """Format whole rupees using lakh/crore grouping: 'NPR 1,25,000' / 'रु १,२५,०००'."""
    grouped = _indian_grouping(int(amount))
    if lang == "ne":
        return "रू " + to_devanagari_digits(grouped)
    return f"NPR {grouped}"


def format_date_pretty(value: date, lang: str = "en") -> str:
    """'22 Oct 2026 (5 Kartik 2083 BS)' style label; falls back to Gregorian only."""
    greg = f"{value.day} {value.strftime('%b %Y')}"
    try:
        bs = gregorian_to_bs(value)
    except DateOutOfRangeError:
        return greg
    month = bs.month_name("ne" if lang == "ne" else "en")
    bs_label = f"{bs.day} {month} {bs.year}"
    if lang == "ne":
        bs_label = to_devanagari_digits(bs_label)
    return f"{greg} ({bs_label} BS)"
