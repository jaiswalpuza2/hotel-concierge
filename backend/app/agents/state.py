"""Typed LangGraph state for one concierge conversation thread."""
from __future__ import annotations

from typing import Annotated, Any, TypedDict

MAX_HISTORY = 60


def append_capped(left: list[dict[str, Any]] | None, right: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Reducer: append new messages, keeping only the latest ``MAX_HISTORY``."""
    return ((left or []) + (right or []))[-MAX_HISTORY:]


class ConciergeState(TypedDict, total=False):
    """Everything the agents share.

    Keys marked *persistent* survive across turns through the checkpointer;
    the rest are reset by the ``ingest`` node at the start of every turn.
    """

    # --- identity ---
    session_id: str
    conversation_id: str
    # --- input for this turn ---
    user_text: str
    ui_language: str | None
    channel: str  # "chat" | "voice"
    # --- language ---
    input_style: str  # "en" | "ne" | "ne_roman"
    language: str  # reply language "en" | "ne"
    reply_style: str  # "en" | "ne" | "ne_roman"
    date_note: str
    # --- persistent ---
    messages: Annotated[list[dict[str, Any]], append_capped]
    handoff_active: bool
    handoff_ticket_ref: str | None
    active_quotes: list[dict[str, Any]]
    last_intent: str
    # --- per-turn working memory ---
    intent: str
    route: str
    scratch: list[dict[str, Any]]
    retrieved: list[dict[str, Any]]
    retrieval_attempts: int
    retrieval_query: str
    pending_tool_calls: list[dict[str, Any]]
    tool_iterations: int
    tool_failures: int
    tool_log: list[dict[str, Any]]
    side_effects: list[dict[str, Any]]
    answer: str
    citations: list[dict[str, Any]]
    handoff_reason: str | None
    handoff_priority: str
    notification_status: str | None
    confidence: float
