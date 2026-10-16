"""Select the configured LLM provider."""
from __future__ import annotations

from functools import lru_cache

import structlog

from app.config import get_settings
from app.llm.base import LLMProvider
from app.llm.providers import AnthropicProvider, OpenAICompatibleProvider

logger = structlog.get_logger(__name__)


@lru_cache(maxsize=1)
def get_llm() -> LLMProvider:
    """Return the process-wide LLM provider chosen by ``LLM_PROVIDER``.

    ``mock`` returns an offline rule-based model so the whole product can be
    demoed and tested with no API key.
    """
    settings = get_settings()
    key = settings.llm_api_key.get_secret_value()
    provider = settings.llm_provider
    logger.info("llm.selected", provider=provider, model=settings.llm_model)

    if provider == "mock":
        from app.llm.mock import MockProvider

        return MockProvider()
    if provider == "anthropic":
        return AnthropicProvider(
            model=settings.llm_model,
            api_key=key,
            base_url=settings.llm_base_url,
            default_temperature=settings.llm_temperature,
            default_max_tokens=settings.llm_max_tokens,
        )
    base_url = settings.llm_base_url
    if provider == "ollama" and not base_url:
        base_url = "http://localhost:11434/v1"
    return OpenAICompatibleProvider(
        model=settings.llm_model,
        api_key=key,
        base_url=base_url,
        default_temperature=settings.llm_temperature,
        default_max_tokens=settings.llm_max_tokens,
    )
