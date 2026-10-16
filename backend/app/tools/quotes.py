"""Signed, expiring price quotes.

``check_room_availability`` / ``get_room_price`` return a ``quote_id``.
``book_room`` only accepts a valid quote_id, so the model can never book dates,
a room type or a price the guest was not shown. The token is stateless (HMAC), so
it works across workers and restarts and cannot be forged by the model.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from datetime import date


class QuoteError(ValueError):
    """Quote token is malformed, tampered with, or expired."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Quote:
    """The facts a quote commits to."""

    room_type_id: str
    check_in: date
    check_out: date
    guests: int
    total_npr: int
    expires_at: int


def _sign(secret: str, body: str) -> str:
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()[:32]


def make_quote_token(
    secret: str,
    *,
    room_type_id: str,
    check_in: date,
    check_out: date,
    guests: int,
    total_npr: int,
    ttl_seconds: int = 1800,
    now: float | None = None,
) -> str:
    """Create a signed quote token valid for ``ttl_seconds`` (default 30 min)."""
    issued = time.time() if now is None else now
    payload = {
        "rt": room_type_id,
        "ci": check_in.isoformat(),
        "co": check_out.isoformat(),
        "g": guests,
        "t": total_npr,
        "x": int(issued + ttl_seconds),
    }
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
    return f"{body}.{_sign(secret, body)}"


def verify_quote_token(secret: str, token: str, *, now: float | None = None) -> Quote:
    """Validate a token and return its contents.

    Raises:
        QuoteError: ``quote_invalid`` (bad format / signature) or ``quote_expired``.
    """
    try:
        body, signature = token.strip().rsplit(".", 1)
    except ValueError as exc:
        raise QuoteError("quote_invalid", "Quote id is malformed") from exc
    if not hmac.compare_digest(signature, _sign(secret, body)):
        raise QuoteError("quote_invalid", "Quote id is not valid")
    try:
        data = json.loads(base64.urlsafe_b64decode(body.encode()))
        quote = Quote(
            room_type_id=str(data["rt"]),
            check_in=date.fromisoformat(data["ci"]),
            check_out=date.fromisoformat(data["co"]),
            guests=int(data["g"]),
            total_npr=int(data["t"]),
            expires_at=int(data["x"]),
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise QuoteError("quote_invalid", "Quote id is corrupted") from exc
    current = time.time() if now is None else now
    if current > quote.expires_at:
        raise QuoteError("quote_expired", "This price quote has expired; please check availability again")
    return quote
