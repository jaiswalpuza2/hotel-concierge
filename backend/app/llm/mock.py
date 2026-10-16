"""Offline rule-based "LLM" for demos, CI and development without an API key.

It is NOT intelligent: it reads the task markers the real prompts contain and
follows fixed rules (regex extraction + templated answers). It exists so the whole
pipeline -- routing, tool calls, booking guard, handoff, notifications, WebSocket,
UI -- can be exercised end-to-end for free. Set ``LLM_PROVIDER=openai|anthropic|ollama``
for real conversations.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date
from typing import Any

from app.agents.intent import (
    AVAILABILITY, BOOK, CANCEL, FAQ, RESTAURANT, SERVICE, SMALLTALK, STATUS, classify_intent,
)
from app.llm.base import LLMProvider, LLMResponse, ToolCall
from app.utils.bikram_sambat import normalize_digits
from app.utils.nepali_text import extract_bs_dates
from app.utils.timeutil import nepal_today

_TASK_RE = re.compile(r"\[\[TASK:(\w+)\]\]")
_LANG_RE = re.compile(r"\[\[LANG:(\w+)\]\]")
_STYLE_RE = re.compile(r"\[\[STYLE:(\w+)\]\]")
_ISO_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
_REF_RE = re.compile(r"\b(HH-[0-9A-Fa-f]{8})\b")
_PHONE_RE = re.compile(r"(?<!\d)(9[78]\d{8})(?!\d)")
_GUESTS_RE = re.compile(r"(\d{1,2})\s*(?:people|persons|person|guests|adults|pax|जना|jana)", re.IGNORECASE)
_NAME_RE = re.compile(r"(?:my name is|name is|i am|i'm|mero naam|मेरो नाम)\s+([A-Za-z\u0900-\u097F][\w\u0900-\u097F .'-]{1,40})", re.IGNORECASE)
_YES_RE = re.compile(r"\b(yes|yeah|yep|confirm|confirmed|go ahead|please do|ok|okay|sure|ho|hunchha|huncha|thik)\b|हुन्छ|हो|ठीक|पक्का|गर्नुहोस्", re.IGNORECASE)
_ROOM_WORDS = {
    "family": "family_suite", "suite": "family_suite", "deluxe": "deluxe",
    "standard": "standard", "conference": "conference_hall", "hall": "conference_hall",
}
_QUOTE_LINE = re.compile(r"- (\w+) \| ([\d-]+) -> ([\d-]+) \| guests (\d+) \| total (\d+) \| quote_id=(\S+)")


def _marker(regex: re.Pattern[str], text: str, default: str) -> str:
    m = regex.search(text)
    return m.group(1) if m else default


def _say(lang_style: str, en: str, ne: str, roman: str) -> str:
    return {"en": en, "ne": ne}.get(lang_style, roman)


class MockProvider(LLMProvider):
    """Deterministic stand-in for a real model."""

    name = "mock"

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        task = _marker(_TASK_RE, system, "smalltalk")
        style = _marker(_STYLE_RE, system, "en")
        users = [m["content"] for m in messages if m["role"] == "user"]
        last_user = users[-1] if users else ""

        if task == "classify":
            return LLMResponse(text=json.dumps({"intent": classify_intent(last_user)}))
        if task in ("rewrite", "translate"):
            return LLMResponse(text=last_user)
        if task == "rag_answer":
            return LLMResponse(text=self._rag(system, style))
        if task == "tool_agent":
            return self._tool_agent(messages, system, style, users)
        return LLMResponse(text=self._smalltalk(last_user, style))

    # ------------------------------------------------------------------

    @staticmethod
    def _smalltalk(text: str, style: str) -> str:
        if re.search(r"thank|धन्यवाद|dhanyabad", text, re.IGNORECASE):
            return _say(style, "You're welcome! Anything else I can help with?",
                        "धन्यवाद! अरू केही सहयोग चाहिन्छ?", "Dhanyabad! Aru kehi sahayog chahinchha?")
        return _say(style,
                    "Hello! I'm the Himalayan Heritage Hotel concierge. Ask me about rooms, prices, bookings or the restaurant.",
                    "नमस्ते! म हिमालयन हेरिटेज होटलको कन्सियर्ज हुँ। कोठा, भाडा, बुकिङ वा रेस्टुरेन्टबारे सोध्नुहोस्।",
                    "Namaste! Ma Himalayan Heritage Hotel ko concierge hu. Kotha, bhada, booking wa restaurant bare sodhnuhos.")

    @staticmethod
    def _rag(system: str, style: str) -> str:
        docs = re.findall(r"\[(\d+)\] \(([^)]*)\)\n(.*?)(?=\n\n\[\d+\] \(|\Z)", system, re.DOTALL)
        if not docs:
            return _say(style, "I don't have that information.", "मसँग जानकारी छैन।", "Malai thaha chaina.")
        _num, source, content = docs[0]
        snippet = " ".join(content.split())[:420]
        return f"{snippet} ({source})"

    def _tool_agent(self, messages: list[dict[str, Any]], system: str, style: str, users: list[str]) -> LLMResponse:
        # 1) A tool result is waiting to be explained.
        if messages and messages[-1]["role"] == "tool":
            retry = self._retry_call(messages)
            if retry is not None:
                return LLMResponse(tool_calls=[retry])
            return LLMResponse(text=self._explain_tool(messages, style))

        text = " ".join(users[-6:])
        last = users[-1] if users else ""
        norm = normalize_digits(text)
        intent = classify_intent(last)
        today = nepal_today()

        dates = [date.fromisoformat(d) for d in _ISO_RE.findall(norm)]
        if len(dates) < 2:
            dates = [m.gregorian for m in extract_bs_dates(norm, today)] or dates
        guests_m = _GUESTS_RE.findall(norm)
        guests = int(guests_m[-1]) if guests_m else (2 if re.search(r"\bcouple\b|\bdouble\b", norm, re.I) else None)
        room = next((v for k, v in _ROOM_WORDS.items() if k in norm.lower()), None)
        ref = (_REF_RE.findall(norm) or [None])[-1]
        phone = (_PHONE_RE.findall(norm) or [None])[-1]
        quotes = [
            {"room_type": m[0], "check_in": m[1], "check_out": m[2], "guests": int(m[3]), "total": int(m[4]), "quote_id": m[5]}
            for m in _QUOTE_LINE.findall(system)
        ]
        wants_yes = bool(_YES_RE.search(last))

        name_m = _NAME_RE.search(text)
        if quotes and (intent in (BOOK, SMALLTALK) or wants_yes or (phone and name_m) or (room and not dates)) and intent not in (CANCEL, STATUS):
            chosen = next((q for q in quotes if room and q["room_type"] == room), quotes[-1])
            if not phone or not name_m:
                return LLMResponse(text=_say(style,
                    "To book this I need your full name and a 10-digit mobile number.",
                    "बुक गर्न मलाई तपाईंको पूरा नाम र १० अङ्कको मोबाइल नम्बर चाहिन्छ।",
                    "Book garna malai tapaiko pura naam ra 10 anka ko mobile number chahinchha."))
            return LLMResponse(tool_calls=[ToolCall(
                id=f"call_{uuid.uuid4().hex[:8]}", name="book_room",
                arguments={"quote_id": chosen["quote_id"], "guest_name": name_m.group(1).strip(" ."),
                           "phone": phone, "preferred_language": "ne" if style != "en" else "en",
                           "user_confirmed": wants_yes})])

        if intent in (AVAILABILITY, BOOK):
            if len(dates) < 2 or not guests:
                return LLMResponse(text=_say(style,
                    "Sure! Please tell me your check-in and check-out dates and how many guests.",
                    "हुन्छ! कृपया चेक-इन, चेक-आउट मिति र अतिथि संख्या भन्नुहोस्।",
                    "Hunchha! Kripaya check-in, check-out miti ra atithi sankhya bhannuhos."))
            args: dict[str, Any] = {"check_in": dates[0].isoformat(), "check_out": dates[1].isoformat(), "guests": guests}
            if room:
                args["room_type"] = room
            return LLMResponse(tool_calls=[ToolCall(id=f"call_{uuid.uuid4().hex[:8]}", name="check_room_availability", arguments=args)])

        prior_cancel = any(classify_intent(u) == CANCEL for u in users[-6:])
        if ref and phone and (intent in (CANCEL, STATUS) or (wants_yes and prior_cancel)):
            cancelling = intent == CANCEL or prior_cancel
            name = "cancel_booking" if cancelling else "get_booking_status"
            call_args: dict[str, Any] = {"booking_reference": ref, "phone": phone}
            if cancelling:
                first_idx = next((i for i, u in enumerate(users) if _REF_RE.search(normalize_digits(u))), 0)
                call_args["user_confirmed"] = wants_yes and (len(users) - 1) > first_idx
            return LLMResponse(tool_calls=[ToolCall(id=f"call_{uuid.uuid4().hex[:8]}", name=name, arguments=call_args)])
        if intent in (CANCEL, STATUS):
            return LLMResponse(text=_say(style,
                "Please share your booking reference (like HH-3FA85F64) and the phone number you booked with.",
                "कृपया बुकिङ रेफरेन्स (जस्तै HH-3FA85F64) र बुकिङमा प्रयोग गरेको फोन नम्बर दिनुहोस्।",
                "Kripaya booking reference (jastai HH-3FA85F64) ra booking ma prayog gareko phone number dinuhos."))

        if intent in (RESTAURANT, SERVICE):
            return LLMResponse(tool_calls=[ToolCall(id=f"call_{uuid.uuid4().hex[:8]}", name="search_knowledge_base", arguments={"query": last})])

        query = last if intent == FAQ or last else "hotel information"
        return LLMResponse(tool_calls=[ToolCall(id=f"call_{uuid.uuid4().hex[:8]}", name="search_knowledge_base", arguments={"query": query})])

    # ------------------------------------------------------------------

    @staticmethod
    def _retry_call(messages: list[dict[str, Any]]) -> ToolCall | None:
        """Re-issue the previous call after a transient (retryable) failure."""
        try:
            payload = json.loads(messages[-1].get("content", "{}"))
        except json.JSONDecodeError:
            return None
        if payload.get("ok") or not payload.get("error", {}).get("retryable"):
            return None
        for prev in reversed(messages[:-1]):
            if prev["role"] == "assistant" and prev.get("tool_calls"):
                call = prev["tool_calls"][0]
                return ToolCall(id=f"call_{uuid.uuid4().hex[:8]}", name=call["name"], arguments=call["arguments"])
        return None

    @staticmethod
    def _explain_tool(messages: list[dict[str, Any]], style: str) -> str:
        raw = messages[-1].get("content", "{}")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}
        lang = "ne" if style == "ne" else "en"
        if not payload.get("ok"):
            err = payload.get("error", {})
            code = err.get("code")
            details = err.get("details", {})
            if code == "confirmation_required":
                if "summary" in details:
                    s = details["summary"]
                    return _say(style,
                        f"Please confirm: {s['room_type']} from {s['check_in']} to {s['check_out']}, total {s['total_formatted']}. Reply 'yes' to book.",
                        f"कृपया पुष्टि गर्नुहोस्: {s['room_type']}, {s['check_in']} देखि {s['check_out']} सम्म, जम्मा {s['total_formatted']}। बुक गर्न 'हुन्छ' भन्नुहोस्।",
                        f"Kripaya pushti garnuhos: {s['room_type']}, {s['check_in']} dekhi {s['check_out']} samma, jamma {s['total_formatted']}. Book garna 'hunchha' bhannuhos.")
                refund = details.get("refund", {})
                return _say(style,
                    f"Cancelling now would refund {refund.get('refund_percentage', 0)}% ({refund.get('refund_formatted', '')}). Reply 'yes' to cancel and I'll refund per policy (refund shown above).",
                    f"अहिले रद्द गर्दा {refund.get('refund_percentage', 0)}% ({refund.get('refund_formatted', '')}) फिर्ता हुन्छ। रद्द गर्न 'हुन्छ' भन्नुहोस् (refund shown above).",
                    f"Ahile radda garda {refund.get('refund_percentage', 0)}% ({refund.get('refund_formatted', '')}) pheri hunchha. Radda garna 'hunchha' bhannuhos (refund shown above).")
            return _say(style, f"Sorry, I couldn't do that: {err.get('message', 'unknown problem')}.",
                        f"माफ गर्नुहोस्, यो गर्न सकिएन: {err.get('message', '')}।",
                        f"Maaf garnuhos, yo garna sakiyena: {err.get('message', '')}.")
        data = payload.get("data", {})
        if "options" in data:
            options = data["options"]
            if not options:
                return _say(style, "Sorry, no rooms are free for those dates. Would you like to try other dates?",
                            "माफ गर्नुहोस्, ती मितिमा कोठा खाली छैन। अर्को मिति हेर्ने?", "Maaf garnuhos, ti miti ma kotha khali chaina. Arko miti hernu hunchha?")
            lines = "; ".join(f"{o['name']} {o['total_formatted']} ({o['nights']} nights)" for o in options)
            return _say(style, f"For {data['check_in_display']} to {data['check_out_display']}: {lines}. Which room would you like?",
                        f"{data['check_in_display']} देखि {data['check_out_display']} सम्म: {lines}। कुन कोठा चाहनुहुन्छ?",
                        f"{data['check_in_display']} dekhi {data['check_out_display']} samma: {lines}. Kun kotha chahanuhunchha?")
        if "booking_reference" in data and data.get("status") == "confirmed" and "room_number" in data:
            return _say(style,
                f"Booked! Your reference is {data['booking_reference']} - {data['room_type']}, {data['check_in']} to {data['check_out']}, total {data['total_formatted']}. Pay at check-in.",
                f"बुकिङ भयो! तपाईंको रेफरेन्स {data['booking_reference']} — {data['room_type']}, {data['check_in']} देखि {data['check_out']}, जम्मा {data['total_formatted']}। भुक्तानी चेक-इनमा गर्नुहोस्।",
                f"Booking bhayo! Tapaiko reference {data['booking_reference']} - {data['room_type']}, {data['check_in']} dekhi {data['check_out']}, jamma {data['total_formatted']}. Check-in ma payment garnuhos.")
        if "booking_reference" in data:
            return _say(style, f"Booking {data['booking_reference']} is {data['status']} ({data.get('check_in')} to {data.get('check_out')}).",
                        f"बुकिङ {data['booking_reference']} {data['status']} छ।", f"Booking {data['booking_reference']} {data['status']} chha.")
        if "results" in data:
            results = data["results"]
            if not results:
                return _say(style, "I don't have that information.", "मसँग जानकारी छैन।", "Malai thaha chaina.")
            top = " ".join(results[0]["text"].split())[:420]
            return f"{top} ({results[0]['source']})"
        _ = lang
        return _say(style, "Done.", "भयो।", "Bhayo.")
