"""Voice providers: OpenAI Whisper (STT), OpenAI TTS, Google Cloud (STT/TTS), mock tone."""
from __future__ import annotations

import io
import math
import struct
import wave
from typing import Any

import httpx
import structlog

from app.config import get_settings
from app.exceptions import ProviderError
from app.voice.base import SpokenAudio, STTProvider, Transcript, TTSProvider

logger = structlog.get_logger(__name__)

_EXT = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "mp4", "audio/mpeg": "mp3",
        "audio/wav": "wav", "audio/x-wav": "wav", "audio/m4a": "m4a"}


def _ext_for(mime: str) -> str:
    return _EXT.get(mime.split(";")[0].strip().lower(), "webm")


class WhisperSTT(STTProvider):
    """OpenAI Whisper transcription API (supports Nepali: ``language="ne"``)."""

    name = "whisper"

    def __init__(self, api_key: str, model: str = "whisper-1") -> None:
        self._key, self._model = api_key, model

    async def transcribe(self, audio: bytes, mime_type: str, language_hint: str | None = None) -> Transcript:
        data: dict[str, Any] = {"model": self._model, "response_format": "json"}
        if language_hint in ("en", "ne"):
            data["language"] = language_hint
        files = {"file": (f"speech.{_ext_for(mime_type)}", audio, mime_type.split(";")[0] or "audio/webm")}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
                response = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self._key}"}, data=data, files=files,
                )
        except httpx.HTTPError as exc:
            raise ProviderError("Speech service unreachable", code="stt_network_error") from exc
        if response.status_code != 200:
            raise ProviderError("Speech recognition failed", code="stt_failed",
                                details={"status": response.status_code, "body": response.text[:200]})
        return Transcript(text=str(response.json().get("text", "")).strip(), language=language_hint)


class OpenAITTS(TTSProvider):
    """OpenAI text-to-speech. Great for English; Nepali is read with an English-leaning accent."""

    name = "openai"

    def __init__(self, api_key: str, model: str = "tts-1", voice: str = "alloy") -> None:
        self._key, self._model, self._voice = api_key, model, voice

    async def synthesize(self, text: str, language: str) -> SpokenAudio:
        payload = {"model": self._model, "voice": self._voice, "input": text[:3500], "response_format": "mp3"}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
                response = await client.post(
                    "https://api.openai.com/v1/audio/speech",
                    headers={"Authorization": f"Bearer {self._key}"}, json=payload,
                )
        except httpx.HTTPError as exc:
            raise ProviderError("Speech service unreachable", code="tts_network_error") from exc
        if response.status_code != 200:
            raise ProviderError("Speech synthesis failed", code="tts_failed", details={"status": response.status_code})
        return SpokenAudio(response.content, "audio/mpeg")


class GoogleSTT(STTProvider):
    """Google Cloud Speech-to-Text (``ne-NP`` supported). Needs ``google-cloud-speech``."""

    name = "google"

    async def transcribe(self, audio: bytes, mime_type: str, language_hint: str | None = None) -> Transcript:
        try:
            from google.cloud import speech  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ProviderError("Install google-cloud-speech to use STT_PROVIDER=google", code="stt_dependency_missing") from exc
        code = "ne-NP" if language_hint == "ne" else "en-US"
        encoding = (speech.RecognitionConfig.AudioEncoding.OGG_OPUS if "ogg" in mime_type
                    else speech.RecognitionConfig.AudioEncoding.WEBM_OPUS)
        client = speech.SpeechAsyncClient()
        config = speech.RecognitionConfig(encoding=encoding, sample_rate_hertz=48000, language_code=code,
                                          alternative_language_codes=["en-US" if code != "en-US" else "ne-NP"])
        try:
            result = await client.recognize(config=config, audio=speech.RecognitionAudio(content=audio))
        except Exception as exc:
            raise ProviderError("Google speech recognition failed", code="stt_failed") from exc
        text = " ".join(r.alternatives[0].transcript for r in result.results if r.alternatives).strip()
        return Transcript(text=text, language=language_hint)


class GoogleTTS(TTSProvider):
    """Google Cloud Text-to-Speech. Needs ``google-cloud-texttospeech``."""

    name = "google"

    def __init__(self, voice_ne: str, voice_en: str) -> None:
        self._voices = {"ne": ("ne-NP", voice_ne), "en": ("en-US", voice_en)}

    async def synthesize(self, text: str, language: str) -> SpokenAudio:
        try:
            from google.cloud import texttospeech  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ProviderError("Install google-cloud-texttospeech to use TTS_PROVIDER=google", code="tts_dependency_missing") from exc
        code, voice = self._voices.get(language, self._voices["en"])
        client = texttospeech.TextToSpeechAsyncClient()
        try:
            response = await client.synthesize_speech(
                input=texttospeech.SynthesisInput(text=text[:4500]),
                voice=texttospeech.VoiceSelectionParams(language_code=code, name=voice),
                audio_config=texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3),
            )
        except Exception as exc:
            raise ProviderError("Google speech synthesis failed", code="tts_failed") from exc
        return SpokenAudio(response.audio_content, "audio/mpeg")


class MockTTS(TTSProvider):
    """Returns a short pleasant tone (valid WAV) so the playback pipeline can be tested offline."""

    name = "mock"

    async def synthesize(self, text: str, language: str) -> SpokenAudio:
        rate, seconds = 16000, 0.35
        frames = bytearray()
        for i in range(int(rate * seconds)):
            fade = min(1.0, i / 800, (int(rate * seconds) - i) / 800)
            frames += struct.pack("<h", int(9000 * fade * math.sin(2 * math.pi * 523.25 * i / rate)))
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(bytes(frames))
        return SpokenAudio(buffer.getvalue(), "audio/wav")


def build_stt() -> STTProvider | None:
    """STT provider from settings, or ``None`` when voice input is not configured server-side."""
    s = get_settings()
    if s.stt_provider == "whisper":
        key = s.openai_whisper_api_key.get_secret_value()
        return WhisperSTT(key) if key else None
    if s.stt_provider == "google":
        return GoogleSTT() if s.google_application_credentials else None
    return None


def build_tts() -> TTSProvider | None:
    """TTS provider from settings, or ``None`` when spoken replies are not configured."""
    s = get_settings()
    if not s.tts_enabled:
        return None
    if s.tts_provider == "openai":
        key = s.openai_whisper_api_key.get_secret_value() or s.llm_api_key.get_secret_value()
        return OpenAITTS(key) if key else None
    if s.tts_provider == "google":
        return GoogleTTS(s.google_tts_voice_ne, s.google_tts_voice_en) if s.google_application_credentials else None
    if s.tts_provider == "mock":
        return MockTTS()
    return None
