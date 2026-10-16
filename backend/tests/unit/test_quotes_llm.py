"""Quote tokens and LLM message translation tests."""
from __future__ import annotations

from datetime import date

from app.llm.base import extract_json, to_anthropic_messages, to_anthropic_tools, to_openai_messages, to_openai_tools
from app.tools.quotes import QuoteError, make_quote_token, verify_quote_token

SECRET = "unit-test-secret"


def _token(**over):
    base = dict(room_type_id="deluxe", check_in=date(2026, 10, 21), check_out=date(2026, 10, 24),
                guests=2, total_npr=9000, now=1000.0)
    base.update(over)
    return make_quote_token(SECRET, **base)


def test_quote_round_trip():
    q = verify_quote_token(SECRET, _token(), now=1100.0)
    assert (q.room_type_id, q.guests, q.total_npr) == ("deluxe", 2, 9000)


def test_quote_rejects_tampering_wrong_secret_and_expiry():
    token = _token()
    for bad, code in ((token + "x", "quote_invalid"), ("garbage", "quote_invalid")):
        try:
            verify_quote_token(SECRET, bad, now=1100.0)
            raise AssertionError("should fail")
        except QuoteError as exc:
            assert exc.code == code
    for kwargs, code in (({"secret": "other"}, "quote_invalid"), ({"now": 1000.0 + 1801}, "quote_expired")):
        try:
            verify_quote_token(kwargs.get("secret", SECRET), token, now=kwargs.get("now", 1100.0))
            raise AssertionError("should fail")
        except QuoteError as exc:
            assert exc.code == code


def test_openai_translation_serialises_tool_arguments():
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "name": "f", "arguments": {"a": 1}}]},
        {"role": "tool", "tool_call_id": "c1", "name": "f", "content": "{}"},
    ]
    out = to_openai_messages(msgs)
    assert out[2]["tool_calls"][0]["function"]["arguments"] == '{"a": 1}'
    assert out[3] == {"role": "tool", "tool_call_id": "c1", "content": "{}"}
    assert to_openai_tools([{"name": "f", "description": "d", "parameters": {"type": "object"}}])[0]["type"] == "function"


def test_anthropic_translation_merges_turns_and_tool_results():
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "ok", "tool_calls": [{"id": "c1", "name": "f", "arguments": {"a": 1}}]},
        {"role": "tool", "tool_call_id": "c1", "name": "f", "content": "{}"},
        {"role": "user", "content": "and then?"},
    ]
    system, turns = to_anthropic_messages(msgs)
    assert system == "sys"
    assert [t["role"] for t in turns] == ["user", "assistant", "user"]
    assert turns[1]["content"][1] == {"type": "tool_use", "id": "c1", "name": "f", "input": {"a": 1}}
    assert [b["type"] for b in turns[2]["content"]] == ["tool_result", "text"]
    assert to_anthropic_tools([{"name": "f", "parameters": {"type": "object"}}])[0]["input_schema"] == {"type": "object"}


def test_extract_json_is_tolerant():
    assert extract_json('{"intent": "faq"}') == {"intent": "faq"}
    assert extract_json('```json\n{"intent": "faq"}\n```') == {"intent": "faq"}
    assert extract_json('Sure! {"intent": "faq"} done') == {"intent": "faq"}
    assert extract_json("no json here") is None
