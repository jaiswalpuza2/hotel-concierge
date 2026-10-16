"""WebSocket chat + voice endpoint.

Protocol (JSON text frames unless noted)
----------------------------------------
Client -> server
    {"type": "message", "text": "...", "language": "en"|"ne"|null, "speak": bool}
    {"type": "audio_start", "mime": "audio/webm;codecs=opus", "language": "en"|"ne"|null, "speak": bool}
    <binary frames>                      # audio chunks while recording
    {"type": "audio_end"}                # transcribe + answer
    {"type": "ping"}
Server -> client
    {"type": "ready", "session_id": "...", "voice_input": bool, "voice_output": bool}
    {"type": "status", "stage": "routing|retrieving|thinking|tool|answering|notifying|handoff|transcribing|speaking", ...}
    {"type": "transcript", "text": "..."}
    {"type": "message_chunk", "text": "..."}            # typing effect, several per reply
    {"type": "message_end", "reply": {...ChatReply...}}
    {"type": "audio", "mime": "audio/mpeg", "data": "<base64>"}
    {"type": "human_message", "text": "...", "ticket_ref": "HT-..."}   # manager reply (pushed)
    {"type": "handoff_resolved", "text": "..."}                        # pushed
    {"type": "error", "code": "...", "message": "..."}
    {"type": "pong"}
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.exceptions import AppError

logger = structlog.get_logger(__name__)
router = APIRouter()

_CHUNK_WORDS = 3
_CHUNK_DELAY = 0.025


async def _stream_text(ws: WebSocket, text: str) -> None:
    """Send the reply in small chunks for a live typing effect."""
    words = text.split(" ")
    for i in range(0, len(words), _CHUNK_WORDS):
        piece = " ".join(words[i : i + _CHUNK_WORDS]) + (" " if i + _CHUNK_WORDS < len(words) else "")
        await ws.send_json({"type": "message_chunk", "text": piece})
        await asyncio.sleep(_CHUNK_DELAY)


def _origin_allowed(ws: WebSocket) -> bool:
    origin = ws.headers.get("origin")
    if not origin:
        return True  # non-browser clients (tests, curl)
    return origin in get_settings().cors_origins


@router.websocket("/ws/chat")
async def chat_socket(ws: WebSocket, session_id: str | None = None) -> None:
    """Real-time guest chat. Query: ``?session_id=<uuid>`` (generated client-side, reused on reconnect)."""
    runtime = getattr(ws.app.state, "runtime", None)
    if runtime is None or not _origin_allowed(ws):
        await ws.close(code=1008)
        return
    try:
        sid = uuid.UUID(session_id) if session_id else uuid.uuid4()
    except ValueError:
        await ws.close(code=1008)
        return

    await ws.accept()
    sid_str = str(sid)
    await runtime.ws.connect(sid_str, ws)
    await ws.send_json(
        {"type": "ready", "session_id": sid_str, "voice_input": runtime.chat.voice_input_available,
         "voice_output": runtime.chat.voice_output_available}
    )
    logger.info("ws.connected", session_id=sid_str)

    audio_buffer = bytearray()
    audio_meta: dict[str, Any] = {}
    max_audio = get_settings().max_audio_bytes

    async def emit(event: dict[str, Any]) -> None:
        await ws.send_json(event)

    async def deliver(reply) -> None:  # type: ignore[no-untyped-def]
        await _stream_text(ws, reply.text)
        await ws.send_json({"type": "message_end", "reply": reply.to_dict() | {"audio_b64": None}})
        if reply.audio_b64:
            await ws.send_json({"type": "audio", "mime": reply.audio_mime, "data": reply.audio_b64})

    try:
        while True:
            frame = await ws.receive()
            if frame.get("type") == "websocket.disconnect":
                break
            try:
                if frame.get("bytes") is not None:
                    if audio_meta:
                        audio_buffer.extend(frame["bytes"])
                        if len(audio_buffer) > max_audio:
                            audio_buffer.clear()
                            audio_meta.clear()
                            await ws.send_json({"type": "error", "code": "audio_too_large", "message": "Recording is too long."})
                    continue
                raw = frame.get("text")
                if raw is None:
                    continue
                data = json.loads(raw)
                kind = data.get("type")

                if kind == "ping":
                    await ws.send_json({"type": "pong"})
                elif kind == "message":
                    reply = await runtime.chat.handle_message(
                        session_id=sid, text=str(data.get("text", "")), ui_language=data.get("language"), emit=emit
                    )
                    if data.get("speak") and runtime.chat.voice_output_available:
                        speech = await runtime.chat.speak(reply.text, reply.reply_style)
                        if speech:
                            reply.audio_b64, reply.audio_mime = speech
                    await deliver(reply)
                elif kind == "audio_start":
                    audio_buffer.clear()
                    audio_meta.clear()
                    audio_meta.update(
                        mime=str(data.get("mime") or "audio/webm"), language=data.get("language"),
                        speak=bool(data.get("speak", True)),
                    )
                elif kind == "audio_end":
                    if not audio_meta:
                        continue
                    meta, audio = dict(audio_meta), bytes(audio_buffer)
                    audio_buffer.clear()
                    audio_meta.clear()
                    reply = await runtime.chat.handle_audio(
                        session_id=sid, audio=audio, mime_type=meta["mime"], ui_language=meta["language"],
                        want_audio_reply=meta["speak"], emit=emit,
                    )
                    await ws.send_json({"type": "transcript", "text": reply.transcript})
                    await deliver(reply)
                else:
                    await ws.send_json({"type": "error", "code": "unknown_type", "message": f"Unknown message type: {kind}"})
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "code": "bad_json", "message": "Invalid JSON"})
            except AppError as exc:
                await ws.send_json({"type": "error", "code": exc.code, "message": exc.message})
            except WebSocketDisconnect:
                raise
            except Exception:
                logger.exception("ws.unhandled_error", session_id=sid_str)
                await ws.send_json({"type": "error", "code": "internal_error", "message": "Something went wrong."})
    except WebSocketDisconnect:
        pass
    finally:
        await runtime.ws.disconnect(sid_str, ws)
        logger.info("ws.disconnected", session_id=sid_str)
