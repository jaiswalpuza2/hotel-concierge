"""Provider-neutral LLM interface.

Messages and tool schemas use one neutral format; each provider translates it.

Neutral message shapes::

    {"role": "system", "content": "..."}
    {"role": "user", "content": "..."}
    {"role": "assistant", "content": "...", "tool_calls": [{"id": "c1", "name": "x", "arguments": {...}}]}
    {"role": "tool", "tool_call_id": "c1", "name": "x", "content": "<json string>"}

Neutral tool schema::

    {"name": "x", "description": "...", "parameters": {<JSON Schema object>}}
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """A function call requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """Normalised model response."""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)


class LLMProvider(ABC):
    """Abstract chat-completion provider with optional function calling."""

    name: str = "base"

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Run one chat completion and return a normalised response."""


# ---------------------------------------------------------------------------
# Message / tool translation (pure functions, unit-tested)
# ---------------------------------------------------------------------------


def to_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate neutral messages to the OpenAI chat-completions format."""
    out: list[dict[str, Any]] = []
    for msg in messages:
        role = msg["role"]
        if role == "assistant" and msg.get("tool_calls"):
            out.append(
                {
                    "role": "assistant",
                    "content": msg.get("content") or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc.get("arguments", {}), ensure_ascii=False),
                            },
                        }
                        for tc in msg["tool_calls"]
                    ],
                }
            )
        elif role == "tool":
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": msg["tool_call_id"],
                    "content": msg.get("content", ""),
                }
            )
        else:
            out.append({"role": role, "content": msg.get("content", "")})
    return out


def to_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Wrap neutral tool schemas in OpenAI's ``{"type": "function"}`` envelope."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("parameters", {"type": "object", "properties": {}}),
            },
        }
        for t in tools
    ]


def to_anthropic_messages(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Translate neutral messages to Anthropic's format.

    Returns:
        ``(system_prompt, messages)``. System messages are concatenated; tool
        results become ``tool_result`` blocks inside a user turn; consecutive
        turns of the same role are merged (Anthropic requires alternation).
    """
    system_parts: list[str] = []
    turns: list[dict[str, Any]] = []

    def push(role: str, blocks: list[dict[str, Any]]) -> None:
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"].extend(blocks)
        else:
            turns.append({"role": role, "content": list(blocks)})

    for msg in messages:
        role = msg["role"]
        if role == "system":
            system_parts.append(msg.get("content", ""))
        elif role == "user":
            push("user", [{"type": "text", "text": msg.get("content", "")}])
        elif role == "assistant":
            blocks: list[dict[str, Any]] = []
            if msg.get("content"):
                blocks.append({"type": "text", "text": msg["content"]})
            for tc in msg.get("tool_calls", []) or []:
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["name"],
                        "input": tc.get("arguments", {}),
                    }
                )
            if blocks:
                push("assistant", blocks)
        elif role == "tool":
            push(
                "user",
                [
                    {
                        "type": "tool_result",
                        "tool_use_id": msg["tool_call_id"],
                        "content": msg.get("content", ""),
                    }
                ],
            )
    return "\n\n".join(p for p in system_parts if p), turns


def to_anthropic_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate neutral tool schemas to Anthropic's ``input_schema`` format."""
    return [
        {
            "name": t["name"],
            "description": t.get("description", ""),
            "input_schema": t.get("parameters", {"type": "object", "properties": {}}),
        }
        for t in tools
    ]


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def extract_json(text: str) -> dict[str, Any] | None:
    """Parse the first JSON object in ``text`` (tolerates code fences / chatter)."""
    if not text:
        return None
    cleaned = _FENCE_RE.sub("", text.strip())
    try:
        value = json.loads(cleaned)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            value = json.loads(cleaned[start : end + 1])
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None
    return None
