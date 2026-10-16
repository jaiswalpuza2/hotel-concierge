"""Speech-to-text and text-to-speech provider interfaces."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Transcript:
    """Result of speech recognition."""

    text: str
    language: str | None = None


@dataclass
class SpokenAudio:
    """Synthesised speech."""

    data: bytes
    mime_type: str  # e.g. "audio/mpeg"


class STTProvider(ABC):
    """Converts recorded audio to text."""

    name = "stt"

    @abstractmethod
    async def transcribe(self, audio: bytes, mime_type: str, language_hint: str | None = None) -> Transcript:
        """Transcribe one utterance. ``language_hint`` is ``"en"`` or ``"ne"``."""


class TTSProvider(ABC):
    """Converts text to spoken audio."""

    name = "tts"

    @abstractmethod
    async def synthesize(self, text: str, language: str) -> SpokenAudio:
        """Speak ``text`` in ``language`` (``"en"`` or ``"ne"``)."""
