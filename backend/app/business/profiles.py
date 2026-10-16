"""Business-type configuration.

The concierge is configured per business by a ``BusinessProfile`` selected with the
``BUSINESS_TYPE`` setting. The hotel profile ships with a complete tool set and seed
data. The other profiles are knowledge-base-only (no live tools yet): they show where a
new vertical plugs in. To add tools for one, implement a ``ToolExecutor`` (see
``app/tools/hotel_tools.py``) and register it in ``app/agents/deps.py``.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BusinessProfile:
    """Static facts and behaviour switches for one business."""

    id: str
    name: str
    name_ne: str
    kind: str  # human readable, e.g. "mid-range hotel"
    kind_ne: str
    location: str
    facts: tuple[str, ...]
    has_live_tools: bool
    handoff_contact: str = "the manager"
    extra_rules: tuple[str, ...] = field(default_factory=tuple)


HOTEL = BusinessProfile(
    id="hotel",
    name="Himalayan Heritage Hotel",
    name_ne="हिमालयन हेरिटेज होटल",
    kind="40-room mid-range hotel with a restaurant, conference hall and tour desk",
    kind_ne="रेस्टुरेन्ट, सम्मेलन हल र टुर डेस्क भएको ४० कोठे मध्यम स्तरको होटल",
    location="Itahari / Dharan region, Koshi Province, Nepal",
    facts=(
        "Currency is Nepali rupees (NPR). Prices are per room per night.",
        "Check-in from 14:00, check-out by 11:00. Reception is open 24 hours.",
        "Payment for the stay is collected at check-in (cash, eSewa, Khalti, bank transfer).",
        "Room types: Standard, Deluxe, Family Suite, Conference Hall.",
        "Groups of 10+ people, weddings and conferences are handled by the manager.",
    ),
    has_live_tools=True,
    extra_rules=(
        "Never state a room price or availability without calling a tool for the exact dates.",
        "Never book without the guest's explicit 'yes' to the room type, dates and total price.",
        "Cancellation and booking lookups need BOTH the booking reference and the phone number.",
    ),
)

HOSPITAL = BusinessProfile(
    id="hospital",
    name="Himalayan Community Hospital",
    name_ne="हिमालयन सामुदायिक अस्पताल",
    kind="community hospital",
    kind_ne="सामुदायिक अस्पताल",
    location="Nepal",
    facts=("Answer only from the hospital's documents. Never give medical diagnoses.",),
    has_live_tools=False,
    handoff_contact="the duty nurse",
    extra_rules=("For any symptom or emergency, advise calling 102 and hand off immediately.",),
)

COOP = BusinessProfile(
    id="agri_coop",
    name="Himalayan Agricultural Co-operative",
    name_ne="हिमालयन कृषि सहकारी",
    kind="agricultural co-operative",
    kind_ne="कृषि सहकारी संस्था",
    location="Nepal",
    facts=("Answer from the co-operative's price sheets and seasonal calendars.",),
    has_live_tools=False,
    handoff_contact="the co-op secretary",
)

RETAIL = BusinessProfile(
    id="retail",
    name="Himalayan General Store",
    name_ne="हिमालयन जनरल स्टोर",
    kind="retail store",
    kind_ne="खुद्रा पसल",
    location="Nepal",
    facts=("Answer from the product catalogue and store policies.",),
    has_live_tools=False,
    handoff_contact="the store manager",
)

_PROFILES = {p.id: p for p in (HOTEL, HOSPITAL, COOP, RETAIL)}


def get_profile(business_type: str = "hotel") -> BusinessProfile:
    """Return the profile for ``business_type`` (defaults to the hotel)."""
    return _PROFILES.get(business_type, HOTEL)
