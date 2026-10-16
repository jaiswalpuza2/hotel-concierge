"""Booking confirmation / cancellation texts in English, Nepali and Romanized Nepali.

Pure functions, unit-tested. SMS texts are kept short: Devanagari SMS uses UCS-2
encoding (70 characters per segment), so every extra word costs money.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

HOTEL = "Himalayan Heritage Hotel"
HOTEL_NE = "हिमालयन हेरिटेज होटल"


@dataclass(frozen=True)
class Rendered:
    """A message ready to send on both channels."""

    sms: str
    email_subject: str
    email_body: str


def render_booking_confirmation(effect: dict[str, Any], style: str) -> Rendered:
    """Confirmation after ``book_room`` succeeds."""
    s = effect.get("summary", {})
    ref = effect["booking_reference"]
    name = effect.get("guest_name", "")
    room = str(s.get("room_type", "")).replace("_", " ").title()
    ci, co, total = s.get("check_in", ""), s.get("check_out", ""), s.get("total_formatted", "")
    if style == "ne":
        sms = f"{HOTEL_NE}: बुकिङ पक्का! रेफ {ref}, {room}, {ci} देखि {co}, जम्मा {total}। भुक्तानी चेक-इनमा।"
        subject = f"बुकिङ पुष्टि {ref} - {HOTEL_NE}"
        body = (f"नमस्ते {name},\n\n{HOTEL_NE} मा तपाईंको बुकिङ पक्का भएको छ।\n\n"
                f"रेफरेन्स: {ref}\nकोठा: {room}\nचेक-इन: {ci} (दिउँसो २:०० बजेदेखि)\nचेक-आउट: {co} (बिहान ११:०० बजेसम्म)\n"
                f"जम्मा: {total}\n\nभुक्तानी चेक-इनमा नगद, eSewa, Khalti वा बैंक ट्रान्सफरबाट गर्न सकिन्छ।\n"
                f"रद्द वा परिवर्तनका लागि रेफरेन्स र बुकिङ फोन नम्बर चाहिन्छ।\n\nधन्यवाद!")
    elif style == "ne_roman":
        sms = f"{HOTEL}: Booking pakka! Ref {ref}, {room}, {ci} dekhi {co}, jamma {total}. Payment check-in ma."
        subject = f"Booking pushti {ref} - {HOTEL}"
        body = (f"Namaste {name},\n\n{HOTEL} ma tapaiko booking pakka bhayeko chha.\n\n"
                f"Reference: {ref}\nKotha: {room}\nCheck-in: {ci} (2:00 PM dekhi)\nCheck-out: {co} (11:00 AM samma)\n"
                f"Jamma: {total}\n\nPayment check-in ma cash, eSewa, Khalti wa bank transfer bata garna sakinchha.\n"
                f"Radda wa parivartan ko lagi reference ra booking phone number chahinchha.\n\nDhanyabad!")
    else:
        sms = f"{HOTEL}: Booking confirmed! Ref {ref}, {room}, {ci} to {co}, total {total}. Pay at check-in."
        subject = f"Booking confirmed {ref} - {HOTEL}"
        body = (f"Dear {name},\n\nYour booking at {HOTEL} is confirmed.\n\n"
                f"Reference: {ref}\nRoom: {room}\nCheck-in: {ci} (from 2:00 PM)\nCheck-out: {co} (by 11:00 AM)\n"
                f"Total: {total}\n\nPayment is collected at check-in (cash, eSewa, Khalti or bank transfer).\n"
                f"To cancel or change your booking, quote the reference and the phone number you booked with.\n\nThank you!")
    return Rendered(sms, subject, body)


def render_cancellation(effect: dict[str, Any], style: str) -> Rendered:
    """Confirmation after ``cancel_booking`` succeeds."""
    ref = effect["booking_reference"]
    refund = effect.get("refund_formatted", "")
    name = effect.get("guest_name", "")
    if style == "ne":
        sms = f"{HOTEL_NE}: बुकिङ {ref} रद्द भयो। फिर्ता: {refund}।"
        return Rendered(sms, f"बुकिङ रद्द {ref}", f"नमस्ते {name},\n\nतपाईंको बुकिङ {ref} रद्द गरिएको छ। फिर्ता हुने रकम: {refund}।\n\nधन्यवाद।")
    if style == "ne_roman":
        sms = f"{HOTEL}: Booking {ref} radda bhayo. Pheri: {refund}."
        return Rendered(sms, f"Booking radda {ref}", f"Namaste {name},\n\nTapaiko booking {ref} radda gariyeko chha. Pheri hune rakam: {refund}.\n\nDhanyabad.")
    sms = f"{HOTEL}: Booking {ref} cancelled. Refund: {refund}."
    return Rendered(sms, f"Booking cancelled {ref}", f"Dear {name},\n\nYour booking {ref} has been cancelled. Refund due: {refund}.\n\nThank you.")


def render_for_effect(effect: dict[str, Any], style: str) -> Rendered:
    """Pick the template that matches a tool side effect."""
    if effect["type"] == "booking_cancelled":
        return render_cancellation(effect, style)
    return render_booking_confirmation(effect, style)
