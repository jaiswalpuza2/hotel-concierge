"""Pydantic Settings — reads all configuration from environment variables / .env file."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """All application settings. Values are read from environment variables.

    SecretStr fields are redacted in logs and repr output.
    """

    model_config = SettingsConfigDict(
        # backend/.env wins over the repo-root .env (used by docker-compose);
        # real environment variables win over both files.
        env_file=(_BACKEND_DIR / ".env", _BACKEND_DIR.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    db_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5433/hoteldb"
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # ------------------------------------------------------------------
    # JWT Authentication
    # ------------------------------------------------------------------
    jwt_secret_key: SecretStr = SecretStr("CHANGE_ME")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # ------------------------------------------------------------------
    # LLM Provider
    # ------------------------------------------------------------------
    llm_provider: Literal["openai", "anthropic", "ollama", "mock"] = "mock"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: SecretStr = SecretStr("")
    llm_base_url: str = ""
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1024

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------
    embedding_provider: Literal["sentence_transformer", "openai", "hashing"] = "sentence_transformer"
    embedding_model: str = "paraphrase-multilingual-mpnet-base-v2"
    embedding_dimensions: int = 768
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_api_key: SecretStr = SecretStr("")  # falls back to LLM_API_KEY when empty

    # ------------------------------------------------------------------
    # RAG
    # ------------------------------------------------------------------
    retrieval_top_k: int = 5
    retrieval_confidence_threshold: float = 0.35
    max_retrieval_retries: int = 2
    max_tool_retries: int = 2
    reranker_enabled: bool = False
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # ------------------------------------------------------------------
    # SMS Notifications
    # ------------------------------------------------------------------
    sms_provider: Literal["mock", "sparrow"] = "mock"
    sms_sparrow_token: SecretStr = SecretStr("")
    sms_sparrow_from: str = "HimalHotel"

    # ------------------------------------------------------------------
    # Email Notifications
    # ------------------------------------------------------------------
    email_provider: Literal["mock", "smtp"] = "mock"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = "noreply@himalayan-hotel.com"

    # ------------------------------------------------------------------
    # Human Handoff Alerts
    # ------------------------------------------------------------------
    handoff_provider: Literal["mock", "telegram", "slack"] = "mock"
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_chat_id: str = ""
    slack_webhook_url: SecretStr = SecretStr("")

    # ------------------------------------------------------------------
    # Voice
    # ------------------------------------------------------------------
    stt_provider: Literal["whisper", "google", "mock", "none"] = "whisper"
    tts_provider: Literal["google", "openai", "mock", "none"] = "google"
    openai_whisper_api_key: SecretStr = SecretStr("")
    google_application_credentials: str = ""
    google_tts_voice_ne: str = "ne-NP-Standard-A"
    google_tts_voice_en: str = "en-US-Standard-D"

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    app_env: Literal["development", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "DEBUG"
    log_format: Literal["json", "text"] = "json"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8000"]
    max_file_upload_bytes: int = 20_971_520  # 20 MB
    rate_limit_per_minute: int = 60

    # ------------------------------------------------------------------
    # Business Configuration
    # ------------------------------------------------------------------
    # Agent behaviour
    max_tool_iterations: int = 6
    history_window: int = 14
    handoff_alert_language: Literal["en", "ne"] = "en"
    quote_ttl_seconds: int = 1800
    # Voice limits
    max_audio_bytes: int = 5_242_880  # 5 MB per utterance
    tts_enabled: bool = True
    # Manager inbox: shown in alerts so managers can open the dashboard
    dashboard_url: str = "http://localhost:3000/admin/handoffs"

    business_name: str = "Himalayan Heritage Hotel"
    business_type: Literal["hotel", "hospital", "agri_coop", "retail"] = "hotel"
    business_location: str = "Itahari, Sudurpurba Province, Nepal"
    knowledge_base_path: str = "knowledge_base/"

    # ------------------------------------------------------------------
    # Frontend (public)
    # ------------------------------------------------------------------
    next_public_api_url: str = "http://localhost:8000"
    next_public_ws_url: str = "ws://localhost:8000"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        """Accept a comma-separated string or a list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Using lru_cache means the .env file is read exactly once per process.
    In tests, call get_settings.cache_clear() to reload with test values.
    """
    return Settings()
