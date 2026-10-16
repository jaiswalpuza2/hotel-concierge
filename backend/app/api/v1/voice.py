"""HTTP voice endpoints (alternative to the WebSocket audio protocol)."""
from __future__ import annotations

import base64
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field

from app.dependencies import get_runtime
from app.exceptions import ProviderError, ValidationError

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/transcribe", summary="Speech to text")
async def transcribe(
    audio: UploadFile = File(...),  # noqa: B008
    language: Literal["en", "ne"] | None = Form(default=None),
    runtime=Depends(get_runtime),  # noqa: B008
) -> dict:
    """Transcribe an uploaded recording (webm/ogg/mp4/wav) without running the agent."""
    stt = runtime.chat._stt  # noqa: SLF001 - same package, intentional
    if stt is None:
        raise ProviderError("Server-side speech recognition is not configured", code="stt_not_configured")
    data = await audio.read()
    if len(data) < 800 or len(data) > 5_242_880:
        raise ValidationError("Audio must be between 1 KB and 5 MB", code="audio_size_invalid")
    result = await stt.transcribe(data, audio.content_type or "audio/webm", language)
    return {"text": result.text, "language": result.language}


class SpeakRequest(BaseModel):
    """Body of ``POST /voice/speak``."""

    text: str = Field(min_length=1, max_length=600)
    language: Literal["en", "ne"] = "en"


@router.post("/speak", summary="Text to speech")
async def speak(body: SpeakRequest, runtime=Depends(get_runtime)) -> dict:  # noqa: B008
    """Synthesize speech; returns base64 audio."""
    result = await runtime.chat.speak(body.text, "en" if body.language == "en" else "ne")
    if result is None:
        raise ProviderError("Server-side speech synthesis is not configured", code="tts_not_configured")
    data, mime = result
    _ = base64, uuid
    return {"audio_b64": data, "mime": mime}
