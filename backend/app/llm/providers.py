"""Concrete LLM providers over plain HTTPS (httpx) -- no vendor SDKs required."""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import httpx
import structlog

from app.exceptions import ProviderError
from app.llm.base import (
    LLMProvider,
    LLMResponse,
    ToolCall,
    to_anthropic_messages,
    to_anthropic_tools,
    to_openai_messages,
    to_openai_tools,
)

logger = structlog.get_logger(__name__)

_RETRY_STATUS = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 5


async def _post_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    provider: str,
) -> httpx.Response:
    """POST with exponential backoff on rate limits and transient server errors."""
    last: httpx.Response | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = await client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            if attempt == _MAX_ATTEMPTS:
                raise ProviderError(
                    f"{provider} request failed: {exc.__class__.__name__}",
                    code="llm_network_error",
                    details={"provider": provider},
                ) from exc
            await asyncio.sleep(0.5 * 2 ** (attempt - 1))
            continue
        if response.status_code in _RETRY_STATUS and attempt < _MAX_ATTEMPTS:
            # Free-tier token limits reset on a ~60s window, so honour the
            # server's retry-after instead of a fixed short backoff.
            try:
                delay = float(response.headers.get("retry-after", ""))
            except ValueError:
                delay = 0.0
            delay = min(max(delay, 0.5 * 2 ** (attempt - 1)), 65.0)
            logger.warning("llm.retrying", provider=provider, status=response.status_code, attempt=attempt, delay=delay)
            await asyncio.sleep(delay)
            last = response
            continue
        return response
    assert last is not None  # pragma: no cover
    return last


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI chat-completions API, also used for Ollama / vLLM / OpenRouter.

    Args:
        model: Model name, e.g. ``gpt-4o-mini`` or ``llama3.1``.
        api_key: Bearer token (may be empty for local Ollama).
        base_url: API root. Empty -> ``https://api.openai.com/v1``.
        default_temperature: Used when ``chat`` is called without a temperature.
        default_max_tokens: Used when ``chat`` is called without ``max_tokens``.
    """

    name = "openai"

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = "",
        default_temperature: float = 0.2,
        default_max_tokens: int = 1024,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self._is_openai = "api.openai.com" in self._base_url
        self._temperature = default_temperature
        self._max_tokens = default_max_tokens

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": to_openai_messages(messages),
        }
        limit = max_tokens or self._max_tokens
        # OpenAI's current models want max_completion_tokens; most other servers still use max_tokens.
        payload["max_completion_tokens" if self._is_openai else "max_tokens"] = limit
        payload["temperature"] = self._temperature if temperature is None else temperature
        if tools:
            payload["tools"] = to_openai_tools(tools)
            payload["tool_choice"] = "auto"

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        url = f"{self._base_url}/chat/completions"
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            response = await _post_with_retry(client, url, headers=headers, payload=payload, provider="openai")
            # Some reasoning models reject a custom temperature: retry once without it.
            if response.status_code == 400 and "temperature" in response.text.lower():
                payload.pop("temperature", None)
                response = await _post_with_retry(client, url, headers=headers, payload=payload, provider="openai")

        if response.status_code != 200:
            raise ProviderError(
                "LLM provider returned an error",
                code="llm_http_error",
                details={"status": response.status_code, "body": response.text[:300]},
            )
        return self._parse(response.json())

    @staticmethod
    def _parse(data: dict[str, Any]) -> LLMResponse:
        try:
            choice = data["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Malformed LLM response", code="llm_bad_response") from exc

        calls: list[ToolCall] = []
        for raw in message.get("tool_calls") or []:
            fn = raw.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {"_raw": fn.get("arguments", "")}
            calls.append(
                ToolCall(
                    id=raw.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                    name=fn.get("name", ""),
                    arguments=args if isinstance(args, dict) else {"_raw": args},
                )
            )
        usage = data.get("usage") or {}
        return LLMResponse(
            text=message.get("content") or "",
            tool_calls=calls,
            finish_reason=choice.get("finish_reason") or "stop",
            usage={
                "prompt_tokens": int(usage.get("prompt_tokens", 0)),
                "completion_tokens": int(usage.get("completion_tokens", 0)),
            },
        )


class AnthropicProvider(LLMProvider):
    """Anthropic Messages API with tool use."""

    name = "anthropic"

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = "",
        default_temperature: float = 0.2,
        default_max_tokens: int = 1024,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._base_url = (base_url or "https://api.anthropic.com").rstrip("/")
        self._temperature = default_temperature
        self._max_tokens = default_max_tokens

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        system, turns = to_anthropic_messages(messages)
        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens or self._max_tokens,
            "messages": turns,
            "temperature": self._temperature if temperature is None else temperature,
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = to_anthropic_tools(tools)

        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        url = f"{self._base_url}/v1/messages"
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            response = await _post_with_retry(client, url, headers=headers, payload=payload, provider="anthropic")
            if response.status_code == 400 and "temperature" in response.text.lower():
                payload.pop("temperature", None)
                response = await _post_with_retry(client, url, headers=headers, payload=payload, provider="anthropic")

        if response.status_code != 200:
            raise ProviderError(
                "LLM provider returned an error",
                code="llm_http_error",
                details={"status": response.status_code, "body": response.text[:300]},
            )
        data = response.json()
        text_parts: list[str] = []
        calls: list[ToolCall] = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                calls.append(
                    ToolCall(id=block["id"], name=block["name"], arguments=block.get("input") or {})
                )
        usage = data.get("usage") or {}
        return LLMResponse(
            text="".join(text_parts),
            tool_calls=calls,
            finish_reason=data.get("stop_reason") or "stop",
            usage={
                "prompt_tokens": int(usage.get("input_tokens", 0)),
                "completion_tokens": int(usage.get("output_tokens", 0)),
            },
        )
