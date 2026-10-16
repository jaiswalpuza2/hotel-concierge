"""Intent routing and handoff trigger tests."""
from __future__ import annotations

from app.agents import intent as I
from app.handoff import triggers as T


def test_intents_english():
    assert I.classify_intent("I want to book a room") == I.BOOK
    assert I.classify_intent("Do you have a deluxe room for 2 people?") == I.AVAILABILITY
    assert I.classify_intent("What time is check-out?") == I.FAQ
    assert I.classify_intent("please cancel my booking") == I.CANCEL
    assert I.classify_intent("airport pickup please") == I.SERVICE
    assert I.classify_intent("table for 4 tonight") == I.RESTAURANT
    assert I.classify_intent("hello") == I.SMALLTALK
    assert I.classify_intent("what is the capital of france") == I.UNKNOWN


def test_intents_nepali_and_romanized():
    assert I.classify_intent("Mero booking cancel garna paryo") == I.CANCEL
    assert I.classify_intent("Dashain ko bela ma family suite kati parcha?") == I.AVAILABILITY
    assert I.classify_intent("कोठा खाली छ?") == I.AVAILABILITY
    assert I.classify_intent("नमस्ते") == I.SMALLTALK


def test_short_words_match_whole_words_only():
    assert I.classify_intent("this is separate") == I.UNKNOWN  # 'rate' inside 'separate'


def test_acknowledgements():
    assert all(I.is_acknowledgement(t) for t in ("yes", "ok", "हुन्छ", "hajur", "Yes!"))
    assert not I.is_acknowledgement("yes please book the deluxe")


def test_handoff_triggers():
    cases = {
        "I want to complain about the room": T.REASON_COMPLAINT,
        "I need an ambulance now": T.REASON_EMERGENCY,
        "I want a refund": T.REASON_REFUND,
        "I was charged twice": T.REASON_PAYMENT,
        "can I speak to a manager": T.REASON_HUMAN,
        "we are 15 people": T.REASON_GROUP,
        "wedding reception booking": T.REASON_GROUP,
        "मलाई गुनासो छ": T.REASON_COMPLAINT,
        "manager sanga kura garna paryo": T.REASON_HUMAN,
        "९ जना आउँछौं": None,
        "१५ जना आउँछौं": T.REASON_GROUP,
    }
    for text, reason in cases.items():
        decision = T.check_text_triggers(text)
        assert (decision.reason if decision else None) == reason, text


def test_emergencies_and_payment_disputes_are_urgent():
    assert T.check_text_triggers("ambulance").priority == "urgent"
    assert T.check_text_triggers("double charge").priority == "urgent"
    assert T.check_text_triggers("complaint").priority == "normal"


def test_normal_requests_do_not_trigger():
    for text in ("Do you have a room for 2 people?", "What time is breakfast?", "5 people tomorrow"):
        assert T.check_text_triggers(text) is None, text


def test_uncertainty_detection():
    assert T.answer_signals_uncertainty("I don't have that information.")
    assert T.answer_signals_uncertainty("मसँग जानकारी छैन।")
    assert not T.answer_signals_uncertainty("Check-out is at 11:00 AM.")
