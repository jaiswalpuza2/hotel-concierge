"""Interfaces the agent graph depends on (implemented in ``runtime.py``; faked in tests)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from app.business.profiles import BusinessProfile
from app.llm.base import LLMProvider
from app.tools.base import ToolExecutor


class KnowledgePort(Protocol):
    """Vector search over the hotel's documents."""

    async def search(self, query: str) -> list[dict[str, Any]]:
        """Return chunk dicts: document_name, section, page_number, content, score."""


@dataclass
class HandoffTicketInfo:
    """What the graph needs back after escalating."""

    ticket_id: str
    ref: str


class HandoffPort(Protocol):
    """Creates a handoff ticket and alerts the human manager."""

    async def escalate(
        self,
        *,
        session_id: str,
        conversation_id: str,
        reason: str,
        priority: str,
        summary: str,
        language: str,
        last_guest_message: str,
    ) -> HandoffTicketInfo:
        """Create the ticket, mark the conversation handed off, alert the manager."""


class NotifierPort(Protocol):
    """Sends booking confirmations over SMS and email."""

    async def send(self, side_effect: dict[str, Any], reply_style: str) -> bool:
        """Return True if at least one channel delivered."""


class Clock(Protocol):
    """Source of 'today' (injectable for tests)."""

    def __call__(self) -> date: ...


@dataclass
class AgentSettings:
    """Tunable limits for loops and history."""

    max_tool_iterations: int = 6
    max_tool_failures: int = 2
    max_rag_attempts: int = 2
    history_window: int = 14


@dataclass
class AgentDeps:
    """All collaborators of the graph, injected once at start-up."""

    llm: LLMProvider
    tools: ToolExecutor
    knowledge: KnowledgePort
    handoff: HandoffPort
    notifier: NotifierPort
    profile: BusinessProfile
    today: Clock
    settings: AgentSettings
