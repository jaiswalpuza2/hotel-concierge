"""The concierge workflow as plain data: nodes, edges and routers.

``graph.py`` turns this spec into a compiled LangGraph; tests execute the very same
spec with a tiny runner, so the routing logic is verified without LangGraph.

Flow (see docs/architecture.md)::

    ingest -> supervisor -+-> smalltalk ---------------------------+
                          +-> retrieve <-> rewrite_query            |
                          |      +-> rag_answer -> guardrail -+     |
                          |      +-> no_kb --------------------+--> compose -> notify? -> finalize
                          +-> tool_agent <-> tool_exec ----------+     |
                          +-> handoff ------------------------------> finalize
                          +-> human_relay --------------------------> finalize
"""
from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import structlog

from app.agents import prompts
from app.agents.events import emit
from app.agents.intent import (
    FAQ, SMALLTALK, TOOL_INTENTS, UNKNOWN, classify_intent, is_acknowledgement,
)
from app.agents.messages import msg, reply_style_for
from app.agents.ports import AgentDeps
from app.agents.state import ConciergeState
from app.exceptions import ProviderError
from app.handoff import triggers
from app.llm.base import extract_json
from app.tools.base import ToolContext
from app.utils.nepali_text import (
    describe_date_mentions, detect_language, extract_bs_dates, resolve_reply_language,
)

logger = structlog.get_logger(__name__)

END = "__end__"
NodeFn = Callable[[ConciergeState], Awaitable[dict[str, Any]]]
RouterFn = Callable[[ConciergeState], str]


@dataclass
class GraphSpec:
    """Declarative description of the workflow graph."""

    entry: str
    nodes: dict[str, NodeFn] = field(default_factory=dict)
    edges: dict[str, str] = field(default_factory=dict)
    conditional: dict[str, tuple[RouterFn, dict[str, str]]] = field(default_factory=dict)


_THANKS_RE = re.compile(r"thank|thx|धन्यवाद|dhanyabad|dhanyawad", re.IGNORECASE)
_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
_LETTER = re.compile(r"[A-Za-z\u0900-\u097F]")
_PHONE_IN_TEXT = re.compile(r"(?<!\d)(\d{3})\d{4}(\d{3})(?!\d)")


def devanagari_ratio(text: str) -> float:
    """Share of letters that are Devanagari (0.0 when there are no letters)."""
    letters = len(_LETTER.findall(text))
    return len(_DEVANAGARI.findall(text)) / letters if letters else 0.0


def mask_phone(value: Any) -> Any:
    """Hide the middle digits of phone numbers before logging / persisting."""
    if isinstance(value, str):
        return _PHONE_IN_TEXT.sub(r"\1****\2", value)
    if isinstance(value, dict):
        return {k: mask_phone(v) for k, v in value.items()}
    if isinstance(value, list):
        return [mask_phone(v) for v in value]
    return value


def _history(state: ConciergeState, window: int) -> list[dict[str, str]]:
    msgs = [
        {"role": m["role"], "content": m["content"]}
        for m in state.get("messages", [])
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    return msgs[-window:]


def _quotes_block(state: ConciergeState) -> str:
    quotes = state.get("active_quotes") or []
    if not quotes:
        return ""
    lines = [
        f"- {q['room_type']} | {q['check_in']} -> {q['check_out']} | guests {q['guests']} | "
        f"total {q['total_npr']} | quote_id={q['quote_id']}"
        for q in quotes
    ]
    return "Active price quotes (use the quote_id for book_room; quotes expire after 30 minutes):\n" + "\n".join(lines)


def _extract_quotes(tool_name: str, data: dict[str, Any], guests_hint: int | None) -> list[dict[str, Any]]:
    """Pull quote summaries out of availability / price tool results."""
    found: list[dict[str, Any]] = []
    if tool_name == "check_room_availability":
        for o in data.get("options", []):
            found.append(
                {
                    "room_type": o["room_type"], "check_in": data["check_in"], "check_out": data["check_out"],
                    "guests": data.get("guests", guests_hint or 1), "total_npr": o["total_npr"], "quote_id": o["quote_id"],
                }
            )
    elif tool_name == "get_room_price" and "quote_id" in data:
        found.append(
            {
                "room_type": data["room_type"], "check_in": data.get("check_in", ""), "check_out": data.get("check_out", ""),
                "guests": guests_hint or 1, "total_npr": data["total_npr"], "quote_id": data["quote_id"],
            }
        )
    return found


def build_spec(deps: AgentDeps) -> GraphSpec:
    """Create the workflow bound to its collaborators."""
    s = deps.settings

    # ------------------------------------------------------------------ nodes

    async def ingest(state: ConciergeState) -> dict[str, Any]:
        text = (state.get("user_text") or "").strip()
        info = detect_language(text)
        resolved = resolve_reply_language(info, state.get("ui_language"))
        style = reply_style_for(resolved.language, resolved.script)
        previous = state.get("reply_style")
        # Short acknowledgements ("ok", "yes") must not flip the conversation's language.
        if previous and (is_acknowledgement(text) or (info.style == "en" and len(text.split()) <= 2)):
            if state.get("ui_language") is None:
                style = previous
        language = "en" if style == "en" else "ne"
        mentions = extract_bs_dates(text, deps.today())
        return {
            "input_style": info.style,
            "language": language,
            "reply_style": style,
            "date_note": describe_date_mentions(mentions),
            "messages": [{"role": "user", "content": text}],
            "intent": "", "route": "", "scratch": [], "pending_tool_calls": [],
            "retrieved": [], "retrieval_attempts": 0, "retrieval_query": "",
            "tool_iterations": 0, "tool_failures": 0, "tool_log": [], "side_effects": [],
            "answer": "", "citations": [], "handoff_reason": None, "handoff_priority": "normal",
            "notification_status": None, "confidence": 1.0,
        }

    async def supervisor(state: ConciergeState) -> dict[str, Any]:
        await emit({"type": "status", "stage": "routing"})
        text = state.get("user_text", "")
        if state.get("handoff_active"):
            return {"intent": "handoff_active", "route": "human_relay"}
        decision = triggers.check_text_triggers(text)
        if decision:
            return {"intent": "handoff", "route": "handoff",
                    "handoff_reason": decision.reason, "handoff_priority": decision.priority}

        intent = classify_intent(text)
        previous = state.get("last_intent", "")
        if previous in TOOL_INTENTS and (
            (intent in (SMALLTALK, UNKNOWN) and is_acknowledgement(text)) or intent == UNKNOWN
        ):
            intent = previous  # the guest is answering our last question
        if intent == UNKNOWN:
            try:
                resp = await deps.llm.chat(
                    [
                        {"role": "system", "content": f"[[TASK:classify]]\n{prompts.CLASSIFY_PROMPT}"},
                        {"role": "user", "content": text},
                    ],
                    temperature=0.0,
                    max_tokens=40,
                )
                parsed = extract_json(resp.text) or {}
                guess = str(parsed.get("intent", "")).strip()
                intent = {"booking": "booking", "availability": "availability", "cancel": "cancel",
                          "booking_status": "booking_status", "service": "service",
                          "restaurant": "restaurant", "faq": FAQ, "smalltalk": SMALLTALK}.get(guess, UNKNOWN)
                if guess == "handoff":
                    return {"intent": "handoff", "route": "handoff", "handoff_reason": triggers.REASON_HUMAN}
            except ProviderError:
                logger.warning("supervisor.classify_failed")
        if intent == SMALLTALK:
            route = "smalltalk"
        elif intent in TOOL_INTENTS and deps.profile.has_live_tools:
            route = "tools"
        else:
            route = "rag"
        return {"intent": intent, "route": route}

    async def smalltalk(state: ConciergeState) -> dict[str, Any]:
        style = state.get("reply_style", "en")
        key = "thanks" if _THANKS_RE.search(state.get("user_text", "")) else "greeting"
        return {"answer": msg(key, style)}

    # ---- RAG branch

    async def retrieve(state: ConciergeState) -> dict[str, Any]:
        await emit({"type": "status", "stage": "retrieving"})
        query = state.get("retrieval_query") or state.get("user_text", "")
        attempts = state.get("retrieval_attempts", 0) + 1
        try:
            chunks = await deps.knowledge.search(query)
        except Exception:  # vector DB problem must degrade to "unknown", not crash the turn
            logger.exception("retrieve.failed")
            chunks = []
        return {
            "retrieved": chunks, "retrieval_attempts": attempts,
            "confidence": max((float(c.get("score", 0.0)) for c in chunks), default=0.0),
        }

    async def rewrite_query(state: ConciergeState) -> dict[str, Any]:
        try:
            resp = await deps.llm.chat(
                [
                    {"role": "system", "content": f"[[TASK:rewrite]]\n{prompts.REWRITE_PROMPT}"},
                    {"role": "user", "content": state.get("user_text", "")},
                ],
                temperature=0.0,
                max_tokens=40,
            )
            rewritten = resp.text.strip().strip('"')[:200]
        except ProviderError:
            rewritten = ""
        return {"retrieval_query": rewritten or state.get("user_text", "")}

    async def rag_answer(state: ConciergeState) -> dict[str, Any]:
        await emit({"type": "status", "stage": "answering"})
        chunks = state.get("retrieved", [])
        task_text = prompts.RAG_TASK_NE if state.get("language") == "ne" else prompts.RAG_TASK_EN
        system = prompts.build_system_prompt(
            deps.profile, language=state.get("language", "en"), reply_style=state.get("reply_style", "en"),
            task="rag_answer", today=deps.today(), date_note=state.get("date_note", ""),
            extra=task_text + "\n\n" + prompts.format_documents(chunks),
        )
        try:
            resp = await deps.llm.chat(
                [{"role": "system", "content": system}, *_history(state, s.history_window)], max_tokens=600
            )
        except ProviderError:
            return {"handoff_reason": triggers.REASON_LOW_CONF, "answer": "", "intent": "llm_unavailable"}
        seen: set[tuple[str, str | None]] = set()
        citations: list[dict[str, Any]] = []
        for c in chunks:
            key = (c.get("document_name", ""), c.get("section"))
            if key in seen:
                continue
            seen.add(key)
            citations.append({"document_name": c.get("document_name", ""), "section": c.get("section"),
                              "page": c.get("page_number"), "score": round(float(c.get("score", 0.0)), 3)})
        return {"answer": resp.text.strip(), "citations": citations}

    async def guardrail(state: ConciergeState) -> dict[str, Any]:
        answer = state.get("answer", "")
        if not answer or triggers.answer_signals_uncertainty(answer):
            return {"handoff_reason": triggers.REASON_NO_KB, "citations": []}
        return {"handoff_reason": None}

    async def no_kb(state: ConciergeState) -> dict[str, Any]:
        if state.get("intent") == UNKNOWN:
            return {"answer": msg("out_of_scope", state.get("reply_style", "en")), "citations": []}
        return {"handoff_reason": triggers.REASON_NO_KB}

    # ---- Tool branch

    async def tool_agent(state: ConciergeState) -> dict[str, Any]:
        iterations = state.get("tool_iterations", 0) + 1
        if iterations > s.max_tool_iterations:
            return {"handoff_reason": triggers.REASON_LOOP, "tool_iterations": iterations, "pending_tool_calls": []}
        await emit({"type": "status", "stage": "thinking", "iteration": iterations})
        extra = "\n\n".join(x for x in (prompts.TOOL_AGENT_TASK, _quotes_block(state)) if x)
        system = prompts.build_system_prompt(
            deps.profile, language=state.get("language", "en"), reply_style=state.get("reply_style", "en"),
            task="tool_agent", today=deps.today(), date_note=state.get("date_note", ""), extra=extra,
        )
        convo = [{"role": "system", "content": system}, *_history(state, s.history_window), *state.get("scratch", [])]
        try:
            resp = await deps.llm.chat(convo, tools=deps.tools.schemas, max_tokens=700)
        except ProviderError:
            return {"handoff_reason": triggers.REASON_LOW_CONF, "intent": "llm_unavailable",
                    "tool_iterations": iterations, "pending_tool_calls": []}
        if resp.tool_calls:
            calls = [{"id": c.id, "name": c.name, "arguments": c.arguments} for c in resp.tool_calls]
            scratch = [*state.get("scratch", []), {"role": "assistant", "content": resp.text, "tool_calls": calls}]
            return {"scratch": scratch, "pending_tool_calls": calls, "tool_iterations": iterations}
        return {"answer": resp.text.strip(), "pending_tool_calls": [], "tool_iterations": iterations}

    async def tool_exec(state: ConciergeState) -> dict[str, Any]:
        scratch = list(state.get("scratch", []))
        failures = state.get("tool_failures", 0)
        effects = list(state.get("side_effects", []))
        citations = list(state.get("citations", []))
        log = list(state.get("tool_log", []))
        quotes = list(state.get("active_quotes") or [])
        ctx = ToolContext(language=state.get("language", "en"), session_id=state.get("session_id", ""),
                          conversation_id=state.get("conversation_id", ""))
        for call in state.get("pending_tool_calls", []):
            await emit({"type": "status", "stage": "tool", "tool": call["name"]})
            result = await deps.tools.execute(call["name"], call["arguments"], ctx)
            scratch.append({"role": "tool", "tool_call_id": call["id"], "name": call["name"],
                            "content": result.to_llm_json()})
            if not result.ok and result.retryable:
                failures += 1
            if result.side_effect:
                effects.append(result.side_effect)
            citations.extend(result.citations)
            if result.ok and result.data:
                quotes.extend(_extract_quotes(call["name"], result.data, call["arguments"].get("guests")))
            log.append({"name": call["name"], "ok": result.ok, "arguments": mask_phone(call["arguments"]),
                        "error_code": (result.error or {}).get("code")})
        update: dict[str, Any] = {
            "scratch": scratch, "tool_failures": failures, "side_effects": effects, "citations": citations,
            "tool_log": log, "active_quotes": quotes[-6:], "pending_tool_calls": [],
        }
        if failures >= s.max_tool_failures:
            update["handoff_reason"] = triggers.REASON_TOOL_FAIL
        return update

    # ---- Finishing nodes

    async def compose(state: ConciergeState) -> dict[str, Any]:
        answer = (state.get("answer") or "").strip()
        style = state.get("reply_style", "en")
        if not answer:
            return {"answer": msg("error_generic", style)}
        ratio = devanagari_ratio(answer)
        instruction = None
        if style == "ne" and ratio < 0.25 and len(answer) > 12:
            instruction = prompts.TRANSLATE_PROMPT_EN
        elif style == "ne_roman" and ratio > 0.3:
            instruction = prompts.TRANSLATE_PROMPT_ROMAN
        elif style == "en" and ratio > 0.3:
            instruction = prompts.TRANSLATE_PROMPT_TO_EN
        if instruction:
            try:
                resp = await deps.llm.chat(
                    [{"role": "system", "content": f"[[TASK:translate]]\n{instruction}"},
                     {"role": "user", "content": answer}],
                    temperature=0.0, max_tokens=700,
                )
                if resp.text.strip():
                    answer = resp.text.strip()
            except ProviderError:
                logger.warning("compose.translate_failed")
        return {"answer": answer}

    async def notify(state: ConciergeState) -> dict[str, Any]:
        await emit({"type": "status", "stage": "notifying"})
        delivered = False
        for effect in state.get("side_effects", []):
            if effect.get("type") in ("booking_created", "booking_cancelled"):
                try:
                    delivered = await deps.notifier.send(effect, state.get("reply_style", "en")) or delivered
                except Exception:  # confirmations must never break the booking reply
                    logger.exception("notify.failed")
        update: dict[str, Any] = {"notification_status": "sent" if delivered else "failed"}
        if delivered:
            update["answer"] = f"{state.get('answer', '')}\n\n{msg('notif_sent', state.get('reply_style', 'en'))}"
        return update

    async def handoff(state: ConciergeState) -> dict[str, Any]:
        await emit({"type": "status", "stage": "handoff"})
        style = state.get("reply_style", "en")
        reason = state.get("handoff_reason") or triggers.REASON_LOW_CONF
        history = _history(state, 8)
        summary = "\n".join(
            f"{'Guest' if m['role'] == 'user' else 'AI'}: {m['content'][:220]}" for m in history
        )
        try:
            info = await deps.handoff.escalate(
                session_id=state.get("session_id", ""), conversation_id=state.get("conversation_id", ""),
                reason=reason, priority=state.get("handoff_priority", "normal"), summary=summary,
                language=state.get("language", "en"), last_guest_message=state.get("user_text", ""),
            )
        except Exception:
            logger.exception("handoff.failed")
            return {"answer": msg("error_generic", style), "handoff_active": False, "citations": []}
        lead = {
            triggers.REASON_EMERGENCY: msg("emergency", style),
            triggers.REASON_NO_KB: msg("no_answer", style),
            triggers.REASON_TOOL_FAIL: msg("loop_limit", style),
            triggers.REASON_LOOP: msg("loop_limit", style),
        }.get(reason, "")
        if state.get("intent") == "llm_unavailable":
            lead = msg("llm_unavailable", style)
        hold = msg("handoff_hold", style, ref=info.ref)
        return {
            "answer": f"{lead} {hold}".strip() if lead and reason != triggers.REASON_EMERGENCY else
                      (f"{lead}\n\n{hold}" if lead else hold),
            "handoff_active": True, "handoff_ticket_ref": info.ref, "citations": [],
        }

    async def human_relay(state: ConciergeState) -> dict[str, Any]:
        return {"answer": msg("handoff_relay", state.get("reply_style", "en"), ref=state.get("handoff_ticket_ref") or "-")}

    async def finalize(state: ConciergeState) -> dict[str, Any]:
        update: dict[str, Any] = {
            "messages": [{"role": "assistant", "content": state.get("answer", "")}],
            "scratch": [], "pending_tool_calls": [],
        }
        if state.get("route") == "tools" and state.get("intent") in TOOL_INTENTS:
            update["last_intent"] = state["intent"]
        elif state.get("route") in ("smalltalk", "rag", "handoff"):
            update["last_intent"] = ""
        return update

    # ---------------------------------------------------------------- routers

    def after_supervisor(state: ConciergeState) -> str:
        return state.get("route") or "rag"

    def after_retrieve(state: ConciergeState) -> str:
        if state.get("retrieved"):
            return "answer"
        return "rewrite" if state.get("retrieval_attempts", 0) < s.max_rag_attempts else "none"

    def handoff_or(next_node: str) -> RouterFn:
        def router(state: ConciergeState) -> str:
            return "handoff" if state.get("handoff_reason") else next_node
        return router

    def after_tool_agent(state: ConciergeState) -> str:
        if state.get("handoff_reason"):
            return "handoff"
        return "exec" if state.get("pending_tool_calls") else "done"

    def after_compose(state: ConciergeState) -> str:
        wanted = {"booking_created", "booking_cancelled"}
        return "notify" if any(e.get("type") in wanted for e in state.get("side_effects", [])) else "finalize"

    # ------------------------------------------------------------------ wiring

    spec = GraphSpec(entry="ingest")
    spec.nodes = {
        "ingest": ingest, "supervisor": supervisor, "smalltalk": smalltalk, "retrieve": retrieve,
        "rewrite_query": rewrite_query, "rag_answer": rag_answer, "guardrail": guardrail, "no_kb": no_kb,
        "tool_agent": tool_agent, "tool_exec": tool_exec, "compose": compose, "notify": notify,
        "handoff": handoff, "human_relay": human_relay, "finalize": finalize,
    }
    spec.edges = {
        "ingest": "supervisor", "smalltalk": "finalize", "rewrite_query": "retrieve",
        "notify": "finalize", "handoff": "finalize", "human_relay": "finalize", "finalize": END,
    }
    spec.conditional = {
        "supervisor": (after_supervisor, {"smalltalk": "smalltalk", "rag": "retrieve", "tools": "tool_agent",
                                          "handoff": "handoff", "human_relay": "human_relay"}),
        "retrieve": (after_retrieve, {"answer": "rag_answer", "rewrite": "rewrite_query", "none": "no_kb"}),
        "rag_answer": (handoff_or("guardrail"), {"handoff": "handoff", "guardrail": "guardrail"}),
        "guardrail": (handoff_or("compose"), {"handoff": "handoff", "compose": "compose"}),
        "no_kb": (handoff_or("compose"), {"handoff": "handoff", "compose": "compose"}),
        "tool_agent": (after_tool_agent, {"handoff": "handoff", "exec": "tool_exec", "done": "compose"}),
        "tool_exec": (handoff_or("tool_agent"), {"handoff": "handoff", "tool_agent": "tool_agent"}),
        "compose": (after_compose, {"notify": "notify", "finalize": "finalize"}),
    }
    return spec
