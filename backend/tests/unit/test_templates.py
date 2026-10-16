"""Notification templates, handoff alert text and prompt builders."""
from __future__ import annotations

from datetime import date

from app.agents.messages import msg, reply_style_for
from app.agents.prompts import build_system_prompt, format_documents
from app.business.profiles import HOTEL
from app.handoff.providers import HandoffAlert, format_alert
from app.notifications.templates import render_for_effect

EFFECT = {
    "type": "booking_created", "booking_id": "b1", "booking_reference": "HH-3FA85F64", "guest_name": "Puja",
    "summary": {"room_type": "deluxe", "check_in": "21 Oct 2026", "check_out": "24 Oct 2026", "total_formatted": "NPR 9,000"},
}


def test_confirmation_in_all_three_styles_contains_the_essentials():
    for style in ("en", "ne", "ne_roman"):
        out = render_for_effect(EFFECT, style)
        for text in (out.sms, out.email_subject, out.email_body):
            assert "HH-3FA85F64" in text
        assert "9,000" in out.sms or "९,०००" in out.sms or "NPR 9,000" in out.email_body


def test_nepali_sms_is_written_in_devanagari_and_stays_short():
    sms = render_for_effect(EFFECT, "ne").sms
    assert "बुकिङ" in sms
    assert len(sms) <= 140  # keeps the SMS to a couple of UCS-2 segments


def test_cancellation_template_mentions_refund():
    effect = {"type": "booking_cancelled", "booking_id": "b1", "booking_reference": "HH-3FA85F64",
              "guest_name": "Puja", "refund_formatted": "NPR 4,500"}
    assert "4,500" in render_for_effect(effect, "en").sms


def test_static_messages_exist_for_every_style_and_format_cleanly():
    for key in ("greeting", "thanks", "handoff_hold", "handoff_relay", "emergency", "no_answer", "error_generic"):
        for style in ("en", "ne", "ne_roman"):
            text = msg(key, style, ref="HT-1")
            assert text and "{ref}" not in text
    assert reply_style_for("ne", "devanagari") == "ne" and reply_style_for("ne", "latin") == "ne_roman"


def test_prompts_carry_language_rules_and_both_calendars():
    today = date(2026, 10, 13)
    en = build_system_prompt(HOTEL, language="en", reply_style="en", task="tool_agent", today=today)
    ne = build_system_prompt(HOTEL, language="ne", reply_style="ne", task="rag_answer", today=today, date_note="'5 Kartik' = 2026-10-21")
    assert "[[TASK:tool_agent]]" in en and "Bikram Sambat" in en
    assert "[[LANG:ne]]" in ne and "देवनागरी" in ne and "5 Kartik" in ne
    assert "Ashwin 2083 BS" in en.replace("27 Ashwin 2083 BS", "Ashwin 2083 BS")


def test_document_block_is_numbered_with_sources():
    block = format_documents([{"document_name": "faq.md", "section": "Wi-Fi", "content": "Free Wi-Fi."}])
    assert block.startswith("Documents:") and "[1] (faq.md / Wi-Fi)" in block


def test_handoff_alert_is_self_contained():
    alert = HandoffAlert("HT-1", "complaint", "urgent", "ne", "Guest: dirty room", "dirty room", "http://x/admin")
    text = format_alert(alert)
    assert text.startswith("URGENT") and "HT-1" in text and "Nepali" in text and "http://x/admin" in text
