"""Test helpers: fake collaborators and a tiny runner that executes the graph spec.

The runner mimics LangGraph's semantics (partial updates, the ``messages`` reducer,
conditional edges) so the exact routing logic used in production is tested without
LangGraph installed.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from app.agents.graph_spec import END, GraphSpec, build_spec
from app.agents.ports import AgentDeps, AgentSettings, HandoffTicketInfo
from app.agents.state import append_capped
from app.business.profiles import HOTEL
from app.llm.mock import MockProvider
from app.tools.base import ToolContext, ToolResult

TODAY = date(2026, 10, 13)

SCHEMAS = [{"name": n, "description": n, "parameters": {"type": "object", "properties": {}}}
           for n in ("check_room_availability", "book_room", "cancel_booking", "get_booking_status",
                     "search_knowledge_base")]

KB = {
    "check-out": {"document_name": "hotel_policies.md", "section": "Check-in and check-out",
                  "page_number": None, "score": 0.82,
                  "content": "Check-out time is 11:00 AM. Late check-out until 2:00 PM costs NPR 500."},
    "wifi": {"document_name": "faq.md", "section": "Amenities", "page_number": None, "score": 0.7,
             "content": "Free Wi-Fi is available in all rooms and public areas."},
}


class FakeKnowledge:
    async def search(self, query: str) -> list[dict[str, Any]]:
        q = query.lower()
        return [c for k, c in KB.items() if k.replace("-", "") in q.replace("-", "")
                or ("check" in q and "out" in q and k == "check-out")]


class FakeTools:
    """Deterministic stand-in for the DB-backed tool executor."""

    def __init__(self, fail_times: int = 0) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._fail = fail_times

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return SCHEMAS

    async def execute(self, name: str, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        self.calls.append((name, dict(arguments)))
        if self._fail > 0:
            self._fail -= 1
            return ToolResult(ok=False, error={"code": "tool_internal_error", "message": "db down"}, retryable=True)
        if name == "check_room_availability":
            return ToolResult(ok=True, data={
                "check_in": arguments["check_in"], "check_out": arguments["check_out"],
                "check_in_display": arguments["check_in"], "check_out_display": arguments["check_out"],
                "guests": arguments["guests"],
                "options": [{"room_type": "deluxe", "name": "Deluxe", "nights": 3, "total_npr": 9000,
                             "total_formatted": "NPR 9,000", "quote_id": "QUOTE123456.sig"}]})
        if name == "book_room":
            if not arguments.get("user_confirmed"):
                return ToolResult(ok=False, error={"code": "confirmation_required", "message": "confirm",
                                                   "details": {"summary": {"room_type": "deluxe", "check_in": "a", "check_out": "b",
                                                                           "total_formatted": "NPR 9,000"}}})
            return ToolResult(ok=True, data={"booking_reference": "HH-ABCDEF12", "status": "confirmed", "room_number": "201",
                                             "room_type": "deluxe", "check_in": "a", "check_out": "b", "total_formatted": "NPR 9,000"},
                              side_effect={"type": "booking_created", "booking_id": "x", "booking_reference": "HH-ABCDEF12",
                                           "guest_name": arguments["guest_name"], "phone": arguments["phone"], "email": None,
                                           "language": "en", "summary": {}})
        if name == "search_knowledge_base":
            return ToolResult(ok=True, data={"results": []})
        return ToolResult(ok=False, error={"code": "booking_not_found", "message": "Booking not found"})


class FakeHandoff:
    def __init__(self) -> None:
        self.tickets: list[dict[str, Any]] = []

    async def escalate(self, **kw: Any) -> HandoffTicketInfo:
        self.tickets.append(kw)
        return HandoffTicketInfo(ticket_id=f"t{len(self.tickets)}", ref=f"HT-000{len(self.tickets)}")


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send(self, side_effect: dict[str, Any], reply_style: str) -> bool:
        self.sent.append(side_effect)
        return True


class Harness:
    """One simulated conversation thread."""

    def __init__(self, tools: FakeTools | None = None, kb: Any = None) -> None:
        self.tools = tools or FakeTools()
        self.handoff = FakeHandoff()
        self.notifier = FakeNotifier()
        deps = AgentDeps(
            llm=MockProvider(), tools=self.tools, knowledge=kb or FakeKnowledge(), handoff=self.handoff,
            notifier=self.notifier, profile=HOTEL, today=lambda: TODAY, settings=AgentSettings(),
        )
        self.spec: GraphSpec = build_spec(deps)
        self.state: dict[str, Any] = {"session_id": "s1", "conversation_id": "c1"}
        self.trace: list[str] = []

    async def say(self, text: str, ui_language: str | None = None) -> dict[str, Any]:
        self.state.update({"user_text": text, "ui_language": ui_language, "channel": "chat"})
        self.trace = []
        node = self.spec.entry
        for _ in range(80):
            self.trace.append(node)
            update = await self.spec.nodes[node](dict(self.state))
            for key, value in update.items():
                if key == "messages":
                    self.state["messages"] = append_capped(self.state.get("messages"), value)
                else:
                    self.state[key] = value
            if node in self.spec.edges:
                nxt = self.spec.edges[node]
            else:
                router, mapping = self.spec.conditional[node]
                nxt = mapping[router(dict(self.state))]
            if nxt == END:
                return self.state
            node = nxt
        raise AssertionError(f"graph did not terminate: {self.trace}")


def loads(raw: str) -> Any:
    return json.loads(raw)
