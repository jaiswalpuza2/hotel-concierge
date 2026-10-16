"""Fast keyword intent classifier (English, Devanagari Nepali, Romanized Nepali).

The supervisor uses this first (zero latency, zero cost, fully testable). Only
messages it cannot place are sent to the LLM for classification.
"""
from __future__ import annotations

import re

from app.utils.bikram_sambat import normalize_digits

# Intents
EMERGENCY = "emergency"
HANDOFF = "handoff"
BOOK = "booking"
AVAILABILITY = "availability"
CANCEL = "cancel"
STATUS = "booking_status"
SERVICE = "service"
RESTAURANT = "restaurant"
FAQ = "faq"
SMALLTALK = "smalltalk"
UNKNOWN = "unknown"

TOOL_INTENTS = frozenset({BOOK, AVAILABILITY, CANCEL, STATUS, SERVICE, RESTAURANT})
ALL_INTENTS = TOOL_INTENTS | {EMERGENCY, HANDOFF, FAQ, SMALLTALK, UNKNOWN}

_CANCEL = ("cancel", "cancellation", "रद्द", "radda", "cancel garna", "cancel gari")
_STATUS = (
    "booking status", "my booking", "booking id", "booking reference", "check my booking",
    "booking number", "मेरो बुकिङ", "बुकिङ स्थिति", "mero booking", "booking ko status", "booking kasto",
)
_BOOK = (
    "book", "reserve a room", "i want a room", "i need a room", "i'd like a room", "i would like a room",
    "बुक", "आरक्षण", "कोठा चाहिन्छ", "कोठा चाहियो", "kotha chaiyo", "kotha chahiyo", "kotha chahincha",
    "booking garna", "book garna", "book gardinus", "reserve garna",
)
_AVAIL = (
    "available", "availability", "vacant", "vacancy", "free room", "do you have a room", "have a room",
    "rooms left", "price", "rate", "tariff", "how much", "cost", "per night", "cheapest", "discount",
    "खाली", "उपलब्ध", "भाडा", "रेट", "कति पर्छ", "कति पर्ने", "कति पर्दछ", "कति हो", "मूल्य", "कति लाग्छ",
    "kati parcha", "kati parchha", "kati ho", "kati lagcha", "kati lagchha", "khali", "rate kati", "bhada",
    "kotha kati", "kotha khali",
)
_SERVICE = (
    "airport pickup", "airport transfer", "pickup", "pick up", "drop off", "shuttle", "laundry", "tour",
    "safari", "koshi tappu", "dharan tour", "bus park", "taxi",
    "एयरपोर्ट", "पिकअप", "लुगा धुने", "लन्ड्री", "भ्रमण", "ट्याक्सी",
    "airport pickup", "pickup chaiyo", "laundry garna", "ghumna",
)
_RESTAURANT = (
    "table for", "reserve a table", "book a table", "dinner reservation", "lunch reservation",
    "table reservation", "टेबल", "खाना बुक", "table chaiyo", "table book", "bhojan ko lagi table",
)
_FAQ = (
    "check-in", "check in", "checkin", "check-out", "check out", "checkout", "policy", "policies", "wifi", "wi-fi",
    "parking", "menu", "breakfast", "restaurant", "pet", "smoking", "payment", "esewa", "khalti", "card",
    "id proof", "child", "extra bed", "amenities", "facilities", "location", "address", "directions",
    "nearby", "attraction", "festival", "dashain", "tihar", "package", "late check", "early check",
    "gym", "pool", "ac ", "hot water", "what time", "do you allow", "can i bring", "open", "timing",
    "नीति", "वाईफाई", "पार्किङ", "मेनु", "खाजा", "रेस्टुरेन्ट", "धुम्रपान", "भुक्तानी", "इसेवा", "खल्ती",
    "ठेगाना", "नजिक", "समय", "चेक-इन", "चेक आउट", "चेकआउट", "बच्चा", "पाल्तु",
    "kati baje", "wifi cha", "parking cha", "menu ma", "khana", "khaja", "payment kasari", "kasari pugne",
)
_SMALLTALK_RE = re.compile(
    r"^\s*(hi|hello|hey|hii+|good (morning|afternoon|evening|night)|namaste|namaskar|thanks?|thank you|"
    r"thx|ok(ay)?|great|nice|bye|goodbye|नमस्ते|नमस्कार|धन्यवाद|शुभ (प्रभात|रात्री|दिन)|dhanyabad|dhanyawad|"
    r"hajur|ramro|thik cha|thikai cha)[\s!.,?🙏]*$",
    re.IGNORECASE,
)


_AVAIL_RE = re.compile(
    r"(do you have|got|any|is there|are there|looking for|need|want).{0,40}\b(rooms?|suite|deluxe|standard)\b"
    r"|\b(rooms?|suite|deluxe|standard)\b.{0,30}\b(for|from|on|tonight|tomorrow)\b",
    re.IGNORECASE,
)


_ACK_RE = re.compile(
    r"^\s*(yes|yeah|yep|yup|ok(ay)?|sure|confirm(ed)?|go ahead|please do|correct|right|that'?s (right|correct)|"
    r"ho|hunchha|huncha|thik cha|thikai cha|hajur|pakka|हो|हुन्छ|ठीक छ|ठिक छ|पक्का|गर्नुहोस्|हजुर|हजूर)[\s!.,?🙏]*$",
    re.IGNORECASE,
)


def is_acknowledgement(text: str) -> bool:
    """True for short yes/ok replies that continue the previous topic."""
    return bool(_ACK_RE.match(normalize_digits(text.strip())))


def _has(text: str, words: tuple[str, ...]) -> bool:
    for w in words:
        if w in text:
            # short ASCII words must match whole words ("rate" must not hit "separate")
            if w.isascii() and len(w) <= 5 and w.isalpha():
                if re.search(rf"\b{re.escape(w)}\b", text):
                    return True
                continue
            return True
    return False


def classify_intent(text: str) -> str:
    """Return one of ``ALL_INTENTS`` using keyword rules.

    Handoff/emergency triggers are decided separately in ``handoff.triggers``;
    this function only maps ordinary requests.
    """
    low = normalize_digits(text.lower()).strip()
    if not low:
        return SMALLTALK
    if _SMALLTALK_RE.match(low):
        return SMALLTALK
    if _has(low, _CANCEL):
        return CANCEL
    if _has(low, _STATUS):
        return STATUS
    if _has(low, _RESTAURANT):
        return RESTAURANT
    if _has(low, _SERVICE):
        return SERVICE
    if _has(low, _BOOK):
        return BOOK
    if _has(low, _AVAIL) or _AVAIL_RE.search(low):
        return AVAILABILITY
    if _has(low, _FAQ):
        return FAQ
    return UNKNOWN
