"""Nepal time helpers. Nepal is UTC+05:45 year-round (no daylight saving)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

NEPAL_TZ = timezone(timedelta(hours=5, minutes=45), name="NPT")


def nepal_now() -> datetime:
    """Current timezone-aware datetime in Nepal."""
    return datetime.now(tz=NEPAL_TZ)


def nepal_today() -> date:
    """Today's date in Nepal (guests think in local dates, not UTC dates)."""
    return nepal_now().date()
