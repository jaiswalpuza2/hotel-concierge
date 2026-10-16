"""ChatService -- runs one guest turn (text or voice) through the agent graph.

Responsibilities: persist messages, feed handoff state from the database, apply a
timeout and per-session lock, translate failures into a friendly reply, and add
speech-to-text / text-to-speech around the text pipeline.
"""
from __future__ import annotations

import asyncio
import base64
import uuid
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.events import EventCallback, reset_event_callback, set_event_callback
from app.agents.messages import msg
from app.db.models.handoff import HandoffTicket
from app.db.repositories import ConversationRepository
from app.exceptions import AppError, ProviderError, ValidationError
from app.handoff.service import ticket_ref
from app.voice.base import STTProvider, TTSProvider

logger = structlog.get_logger(__name__)

MAX_TEXT_CHARS = 1000
TURN_TIMEOUT_SECONDS = 75
RECURSION_LIMIT = 40


@dataclass
class ChatReply:
    """What the API returns to the UI for one turn."""

    session_id: str
    text: str
    reply_style: str = "en"
    intent: str = ""
    citations: list[dict[str, Any]] = field(default_factory=list)
    handoff_active: bool = False
    handoff_ticket_ref: str | None = None
    transcript: str | None = None
    audio_b64: str | None = None
    audio_mime: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready representation."""
        return {
            "session_id": self.session_id, "text": self.text, "reply_style": self.reply_style,
            "intent": self.intent, "citations": self.citations, "handoff_active": self.handoff_active,
            "handoff_ticket_ref": self.handoff_ticket_ref, "transcript": self.transcript,
            "audio_b64": self.audio_b64, "audio_mime": self.audio_mime,
        }


class ChatService:
    """Orchestrates a concierge conversation."""

    def __init__(
        self,
        graph: Any,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        stt: STTProvider | None,
        tts: TTSProvider | None,
        max_audio_bytes: int,
    ) -> None:
        self._graph = graph
        self._sessions = session_factory
        self._stt = stt
        self._tts = tts
        self._max_audio = max_audio_bytes
        self._locks: dict[str, asyncio.Lock] = {}

    @property
    def voice_input_available(self) -> bool:
        """True when server-side speech recognition is configured."""
        return self._stt is not None

    @property
    def voice_output_available(self) -> bool:
        """True when server-side speech synthesis is configured."""
        return self._tts is not None

    # ------------------------------------------------------------------

    async def handle_message(
        self,
        *,
        session_id: uuid.UUID,
        text: str,
        ui_language: str | None = None,
        channel: str = "chat",
        emit: EventCallback | None = None,
    ) -> ChatReply:
        """Process one guest message and return the concierge's reply."""
        clean = (text or "").strip()
        if not clean:
            raise ValidationError("Message is empty", code="empty_message")
        if len(clean) > MAX_TEXT_CHARS:
            raise ValidationError(
                f"Message is too long (max {MAX_TEXT_CHARS} characters)", code="message_too_long"
            )
        if ui_language not in (None, "en", "ne"):
            ui_language = None

        key = str(session_id)
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            try:
                return await self._run_turn(session_id, clean, ui_language, channel, emit)
            finally:
                if not lock.locked() and len(self._locks) > 500:
                    self._locks.pop(key, None)

    async def _run_turn(
        self, session_id: uuid.UUID, text: str, ui_language: str | None, channel: str, emit: EventCallback | None
    ) -> ChatReply:
        async with self._sessions() as session, session.begin():
            repo = ConversationRepository(session)
            conversation = await repo.get_or_create(session_id, ui_language or "en")
            await repo.add_message(conversation.id, role="user", content=text)
            conversation_id = str(conversation.id)
            handed_off = conversation.status == "handed_off"
            open_ref = None
            if handed_off:
                ticket = (
                    await session.execute(
                        select(HandoffTicket)
                        .where(HandoffTicket.conversation_id == conversation.id, HandoffTicket.status != "resolved")
                        .order_by(HandoffTicket.created_at.desc())
                    )
                ).scalars().first()
                if ticket is None:
                    handed_off = False  # status was stale; AI resumes
                else:
                    open_ref = ticket_ref(ticket.id)

        payload = {
            "session_id": str(session_id), "conversation_id": conversation_id, "user_text": text,
            "ui_language": ui_language, "channel": channel,
            "handoff_active": handed_off, "handoff_ticket_ref": open_ref,
        }
        token = set_event_callback(emit)
        try:
            async with asyncio.timeout(TURN_TIMEOUT_SECONDS):
                result = await self._graph.ainvoke(
                    payload, config={"configurable": {"thread_id": str(session_id)}, "recursion_limit": RECURSION_LIMIT}
                )
        except Exception:
            logger.exception("chat.turn_failed", session_id=str(session_id))
            style = "ne" if ui_language == "ne" else "en"
            result = {"answer": msg("error_generic", style), "reply_style": style, "intent": "error"}
        finally:
            reset_event_callback(token)

        answer = result.get("answer") or msg("error_generic", result.get("reply_style", "en"))
        reply = ChatReply(
            session_id=str(session_id), text=answer, reply_style=result.get("reply_style", "en"),
            intent=result.get("intent", ""), citations=result.get("citations", []),
            handoff_active=bool(result.get("handoff_active")), handoff_ticket_ref=result.get("handoff_ticket_ref"),
        )
        try:
            async with self._sessions() as session, session.begin():
                await ConversationRepository(session).add_message(
                    uuid.UUID(conversation_id), role="assistant", content=answer,
                    intent=reply.intent or None, confidence=result.get("confidence"),
                    tool_calls=result.get("tool_log", []), retrieved_chunks=reply.citations,
                )
                await ConversationRepository(session).set_language(
                    uuid.UUID(conversation_id), "ne" if reply.reply_style != "en" else "en"
                )
        except Exception:
            logger.exception("chat.persist_reply_failed", session_id=str(session_id))
        return reply

    # ------------------------------------------------------------------

    async def handle_audio(
        self,
        *,
        session_id: uuid.UUID,
        audio: bytes,
        mime_type: str,
        ui_language: str | None = None,
        want_audio_reply: bool = True,
        emit: EventCallback | None = None,
    ) -> ChatReply:
        """Voice turn: speech-to-text -> agent -> (optional) text-to-speech."""
        if self._stt is None:
            raise ProviderError("Server-side speech recognition is not configured", code="stt_not_configured")
        if len(audio) > self._max_audio:
            raise ValidationError("Audio is too large", code="audio_too_large", details={"max_bytes": self._max_audio})
        if len(audio) < 800:
            raise ValidationError("Audio is too short", code="audio_too_short")
        if emit:
            await emit({"type": "status", "stage": "transcribing"})
        transcript = await self._stt.transcribe(audio, mime_type, ui_language)
        if not transcript.text:
            raise AppError("I couldn't hear anything. Please try again.", code="no_speech")
        reply = await self.handle_message(
            session_id=session_id, text=transcript.text, ui_language=ui_language, channel="voice", emit=emit
        )
        reply.transcript = transcript.text
        if want_audio_reply and self._tts is not None:
            if emit:
                await emit({"type": "status", "stage": "speaking"})
            try:
                spoken = await self._tts.synthesize(reply.text[:600], "en" if reply.reply_style == "en" else "ne")
                reply.audio_b64 = base64.b64encode(spoken.data).decode("ascii")
                reply.audio_mime = spoken.mime_type
            except ProviderError:
                logger.warning("chat.tts_failed", session_id=str(session_id))
        return reply

    async def speak(self, text: str, reply_style: str) -> tuple[str, str] | None:
        """Synthesize speech for text (used for replies to typed messages when voice mode is on)."""
        if self._tts is None:
            return None
        spoken = await self._tts.synthesize(text[:600], "en" if reply_style == "en" else "ne")
        return base64.b64encode(spoken.data).decode("ascii"), spoken.mime_type
