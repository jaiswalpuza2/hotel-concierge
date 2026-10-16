"""Tool-execution contracts shared by the agent graph and tool implementations."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolContext:
    """Per-call context passed to every tool."""

    language: str = "en"  # reply language: "en" | "ne"
    session_id: str = ""
    conversation_id: str = ""


@dataclass
class ToolResult:
    """Outcome of one tool call.

    Attributes:
        ok: True when the tool did what was asked.
        data: JSON-serialisable payload the model reads.
        error: ``{"code", "message", "details"}`` when ``ok`` is False.
        retryable: True for infrastructure failures (worth retrying / escalating),
            False for business answers like "room unavailable" or "booking not found".
        side_effect: Describes a state change the graph should react to
            (e.g. ``{"type": "booking_created", ...}`` triggers notifications).
        citations: Knowledge-base sources used (for ``search_knowledge_base``).
    """

    ok: bool
    data: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    retryable: bool = False
    side_effect: dict[str, Any] | None = None
    citations: list[dict[str, Any]] = field(default_factory=list)

    def to_llm_json(self) -> str:
        """Serialise for the model (side-effect internals are not shown to it)."""
        payload: dict[str, Any] = {"ok": self.ok}
        if self.ok:
            payload["data"] = self.data or {}
        else:
            payload["error"] = {
                **(self.error or {"code": "unknown", "message": "Unknown error"}),
                "retryable": self.retryable,
            }
        return json.dumps(payload, ensure_ascii=False, default=str)


class ToolExecutor(Protocol):
    """Anything that can run named tools for the agent."""

    @property
    def schemas(self) -> list[dict[str, Any]]:
        """Tool schemas in neutral format (see ``app.llm.base``)."""

    async def execute(
        self, name: str, arguments: dict[str, Any], ctx: ToolContext
    ) -> ToolResult:
        """Run one tool."""
