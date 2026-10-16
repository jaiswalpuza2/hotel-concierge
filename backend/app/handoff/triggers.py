"""Rules that decide when the AI must hand a conversation to a human.

Pure functions (no I/O) so every rule is unit-tested. Matching is deliberately
generous for safety-critical cases (emergencies) and strict for soft cases.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.utils.bikram_sambat import normalize_digits

# Reason slugs stored in ``handoff_tickets.trigger_reason``.
REASON_COMPLAINT = "complaint"
REASON_REFUND = "refund_request"
REASON_PAYMENT = "payment_dispute"
REASON_EMERGENCY = "medical_emergency"
REASON_GROUP = "group_booking"
REASON_HUMAN = "user_requested_human"
REASON_NO_KB = "not_in_knowledge_base"
REASON_TOOL_FAIL = "tool_failure"
REASON_LOW_CONF = "low_confidence"
REASON_LOOP = "tool_loop_limit"

ALL_REASONS = frozenset(
    {
        REASON_COMPLAINT, REASON_REFUND, REASON_PAYMENT, REASON_EMERGENCY, REASON_GROUP,
        REASON_HUMAN, REASON_NO_KB, REASON_TOOL_FAIL, REASON_LOW_CONF, REASON_LOOP,
    }
)

GROUP_THRESHOLD = 10  # guests; hotel_policies.md: groups of 10+ need staff


@dataclass(frozen=True)
class HandoffDecision:
    """Why and how urgently to escalate."""

    reason: str
    priority: str = "normal"  # "urgent" | "normal"


_EMERGENCY = (
    "emergency", "ambulance", "chest pain", "heart attack", "can't breathe", "cannot breathe",
    "unconscious", "bleeding", "fire in", "on fire", "someone is hurt", "need a doctor",
    "poison", "overdose", "suicide",
    "आपतकालीन", "एम्बुलेन्स", "एम्बुलेन्स", "छाती दुख", "सास फेर्न", "बेहोश", "आगलागी", "डाक्टर चाहियो",
    "ambulance chaiyo", "doctor chaiyo", "aagalagi", "behosh", "chhati dukh",
)
_HUMAN = (
    "human", "real person", "speak to someone", "talk to someone", "talk to a person",
    "speak to a manager", "talk to manager", "front desk", "customer service", "call me",
    "म्यानेजर", "मानिसँग", "व्यक्तिसँग", "कर्मचारी", "फोन गर्नुस",
    "manager sanga", "manchhe sanga", "manche sanga", "staff sanga", "phone garnus", "call garnus",
)
_COMPLAINT = (
    "complain", "complaint", "terrible", "horrible", "disgusting", "unacceptable", "worst",
    "dirty", "not working", "broken", "rude", "cockroach", "bed bug", "bedbug", "unhappy",
    "disappointed", "angry",
    "गुनासो", "फोहोर", "खराब", "बिग्रेको", "रिस", "असन्तुष्ट",
    "gunaso", "fohor", "kharab", "bigreko", "ris uthyo",
)
_REFUND = ("refund", "money back", "reimburse", "फिर्ता", "रिफन्ड", "paisa pheri", "paisa farkau", "refund chaiyo")
_PAYMENT = (
    "charged twice", "double charge", "wrong charge", "overcharged", "payment failed",
    "payment dispute", "chargeback", "esewa deducted", "khalti deducted",
    "दोब्बर", "बढी चार्ज", "पैसा काटियो", "paisa katyo", "double paisa",
)
_EVENT = (
    "wedding", "conference", "seminar", "banquet", "party for", "corporate event", "event booking",
    "बिहे", "भोज", "सम्मेलन", "सेमिनार", "bihe", "bhoj",
)
_COUNT_RE = re.compile(
    r"(\d{1,3})\s*(?:\+\s*)?(?:people|persons|person|guests|adults|pax|members|जना|जनाको|jana|janako|manche|mutu)",
    re.IGNORECASE,
)


def _contains(text: str, needles: tuple[str, ...]) -> bool:
    return any(n in text for n in needles)


def largest_party_size(text: str) -> int:
    """Largest 'N people/guests/जना' number mentioned (0 if none)."""
    sizes = [int(m.group(1)) for m in _COUNT_RE.finditer(normalize_digits(text))]
    return max(sizes, default=0)


def check_text_triggers(text: str) -> HandoffDecision | None:
    """Return a decision if the guest's message alone requires a human."""
    low = normalize_digits(text.lower())
    if _contains(low, _EMERGENCY):
        return HandoffDecision(REASON_EMERGENCY, "urgent")
    if _contains(low, _PAYMENT):
        return HandoffDecision(REASON_PAYMENT, "urgent")
    if _contains(low, _REFUND):
        return HandoffDecision(REASON_REFUND)
    if _contains(low, _COMPLAINT):
        return HandoffDecision(REASON_COMPLAINT)
    if _contains(low, _HUMAN):
        return HandoffDecision(REASON_HUMAN)
    if largest_party_size(low) >= GROUP_THRESHOLD or _contains(low, _EVENT):
        return HandoffDecision(REASON_GROUP)
    return None


_UNCERTAIN = (
    "i don't have that information", "i do not have that information", "i'm not sure",
    "i am not sure", "i couldn't find", "i could not find", "i cannot find", "i can't find",
    "not in my documents", "i don't know", "i do not know", "cannot confirm", "can't confirm",
    "मसँग जानकारी छैन", "मलाई थाहा छैन", "थाहा छैन", "पक्का छैन", "भेट्टाउन सकिएन", "जानकारी उपलब्ध छैन",
    "malai thaha chaina", "mero kaha jankari chaina", "jankari chaina", "pakka chaina",
)


def answer_signals_uncertainty(answer: str) -> bool:
    """True when the model's own answer admits it does not know."""
    low = answer.lower()
    return any(marker in low for marker in _UNCERTAIN)
