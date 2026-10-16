"""End-to-end tests of the agent workflow using the offline mock LLM and fake tools."""
from __future__ import annotations

import asyncio

from tests.unit.agent_harness import FakeTools, Harness


def run(coro):
    return asyncio.run(coro)


def test_faq_answers_from_knowledge_base_with_citation():
    async def scenario():
        h = Harness()
        state = await h.say("What time is check-out?")
        assert "11:00" in state["answer"]
        assert state["citations"][0]["document_name"] == "hotel_policies.md"
        assert "retrieve" in h.trace and "rag_answer" in h.trace and "handoff" not in h.trace
    run(scenario())


def test_faq_without_kb_hit_hands_off_instead_of_guessing():
    async def scenario():
        h = Harness()
        state = await h.say("Do you allow pets in the garden?")
        assert h.trace.count("retrieve") == 2  # one retry after query rewrite
        assert h.handoff.tickets and h.handoff.tickets[0]["reason"] == "not_in_knowledge_base"
        assert state["handoff_active"] is True and "HT-0001" in state["answer"]
    run(scenario())


def test_off_topic_gets_polite_scope_message_without_ticket():
    async def scenario():
        h = Harness()
        state = await h.say("Who won the cricket match?")
        assert not h.handoff.tickets
        assert "Himalayan Heritage Hotel" in state["answer"]
    run(scenario())


def test_bikram_sambat_dates_are_converted_and_tool_receives_gregorian():
    async def scenario():
        h = Harness()
        state = await h.say("Do you have a deluxe room for 2 people from 5 to 8 Kartik?")
        name, args = h.tools.calls[0]
        assert name == "check_room_availability"
        assert (args["check_in"], args["check_out"], args["guests"]) == ("2026-10-21", "2026-10-24", 2)
        assert "Deluxe" in state["answer"] and "9,000" in state["answer"]
        assert state["active_quotes"][0]["quote_id"] == "QUOTE123456.sig"
    run(scenario())


def test_full_booking_flow_requires_explicit_confirmation_and_sends_notification():
    async def scenario():
        h = Harness()
        await h.say("Do you have a deluxe room for 2 people from 5 to 8 Kartik?")
        state = await h.say("Deluxe please. My name is Puja Chaudhary, phone 9841234567")
        assert [c for c in h.tools.calls if c[0] == "book_room"][0][1]["user_confirmed"] is False
        assert "confirm" in state["answer"].lower()
        assert not h.notifier.sent
        state = await h.say("yes")
        last_book = [c for c in h.tools.calls if c[0] == "book_room"][-1][1]
        assert last_book["user_confirmed"] is True and last_book["phone"] == "9841234567"
        assert "HH-ABCDEF12" in state["answer"]
        assert h.notifier.sent and h.notifier.sent[0]["booking_reference"] == "HH-ABCDEF12"
        assert "notify" in h.trace
        assert state["notification_status"] == "sent"
    run(scenario())


def test_complaint_triggers_handoff_then_follow_ups_are_relayed():
    async def scenario():
        h = Harness()
        state = await h.say("I want to complain about my room, it is dirty")
        assert h.handoff.tickets[0]["reason"] == "complaint"
        assert state["handoff_active"] and "HT-0001" in state["answer"]
        h.state["handoff_active"] = True  # the service layer feeds this from the DB each turn
        state = await h.say("Hello? Is anyone there?")
        assert "human_relay" in h.trace and "rag_answer" not in h.trace
        assert len(h.handoff.tickets) == 1  # no duplicate ticket
    run(scenario())


def test_emergency_is_urgent_and_shows_emergency_numbers():
    async def scenario():
        h = Harness()
        state = await h.say("I need an ambulance, my friend has chest pain")
        assert h.handoff.tickets[0]["priority"] == "urgent"
        assert "102" in state["answer"]
    run(scenario())


def test_group_booking_goes_to_manager():
    async def scenario():
        h = Harness()
        await h.say("We are 25 people, need rooms for a wedding")
        assert h.handoff.tickets[0]["reason"] == "group_booking"
    run(scenario())


def test_two_tool_infrastructure_failures_escalate():
    async def scenario():
        h = Harness(tools=FakeTools(fail_times=5))
        await h.say("Do you have a deluxe room for 2 people from 5 to 8 Kartik?")
        assert h.handoff.tickets and h.handoff.tickets[0]["reason"] == "tool_failure"
        assert len(h.tools.calls) == 2
    run(scenario())


def test_business_errors_do_not_trigger_handoff():
    async def scenario():
        h = Harness()
        state = await h.say("Check my booking HH-ABCDEF12 phone 9841234567")
        assert not h.handoff.tickets
        assert "Booking not found" in state["answer"] or "couldn't" in state["answer"]
    run(scenario())


def test_romanized_nepali_gets_romanized_reply_and_asks_for_missing_details():
    async def scenario():
        h = Harness()
        state = await h.say("Mero booking cancel garna paryo")
        assert state["reply_style"] == "ne_roman"
        assert "booking reference" in state["answer"] and "Kripaya" in state["answer"]
    run(scenario())


def test_devanagari_input_gets_devanagari_reply():
    async def scenario():
        h = Harness()
        state = await h.say("नमस्ते")
        assert state["reply_style"] == "ne" and "स्वागत" in state["answer"]
    run(scenario())


def test_acknowledgement_does_not_flip_language():
    async def scenario():
        h = Harness()
        await h.say("नमस्ते")
        state = await h.say("ok")
        assert state["reply_style"] == "ne"
    run(scenario())


def test_ui_toggle_forces_nepali_reply_for_english_typing():
    async def scenario():
        h = Harness()
        state = await h.say("hello", ui_language="ne")
        assert state["reply_style"] == "ne"
    run(scenario())


def test_phone_numbers_are_masked_in_tool_log():
    async def scenario():
        h = Harness()
        state = await h.say("Check my booking HH-ABCDEF12 phone 9841234567")
        assert "9841234567" not in str(state["tool_log"])
    run(scenario())
