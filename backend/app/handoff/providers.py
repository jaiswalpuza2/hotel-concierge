"""Manager alert channels: Telegram, Slack, and a logging mock."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx
import structlog

from app.config import get_settings
from app.exceptions import ProviderError

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class HandoffAlert:
    """Everything a manager needs to decide quickly."""

    ref: str
    reason: str
    priority: str
    language: str
    summary: str
    last_guest_message: str
    dashboard_url: str


def format_alert(alert: HandoffAlert) -> str:
    """Plain-text alert body (no markup, so no escaping problems on any channel)."""
    flag = "URGENT - " if alert.priority == "urgent" else ""
    lang = "Nepali" if alert.language == "ne" else "English"
    return (
        f"{flag}Guest needs a human ({alert.ref})\n"
        f"Reason: {alert.reason.replace('_', ' ')}\n"
        f"Guest language: {lang}\n\n"
        f"Last message:\n{alert.last_guest_message[:400]}\n\n"
        f"Recent conversation:\n{alert.summary[-900:]}\n\n"
        f"Reply in the dashboard: {alert.dashboard_url}"
    )


class AlertProvider(ABC):
    """Delivers a handoff alert to the human manager."""

    name = "alert"

    @abstractmethod
    async def send(self, alert: HandoffAlert) -> None:
        """Send the alert. Raises ProviderError on failure."""


class MockAlertProvider(AlertProvider):
    """Logs the alert and keeps it in memory (development / tests)."""

    name = "mock"

    def __init__(self) -> None:
        self.sent: list[HandoffAlert] = []

    async def send(self, alert: HandoffAlert) -> None:
        self.sent.append(alert)
        logger.info("handoff.alert_mock", ref=alert.ref, reason=alert.reason, priority=alert.priority)


class TelegramAlertProvider(AlertProvider):
    """Telegram Bot API ``sendMessage``."""

    name = "telegram"

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._token, self._chat_id = bot_token, chat_id

    async def send(self, alert: HandoffAlert) -> None:
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        payload = {"chat_id": self._chat_id, "text": format_alert(alert)[:4000], "disable_web_page_preview": True}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, json=payload)
        except httpx.HTTPError as exc:
            raise ProviderError("Telegram unreachable", code="telegram_network_error") from exc
        if response.status_code != 200:
            raise ProviderError(
                "Telegram rejected the alert", code="telegram_rejected",
                details={"status": response.status_code, "body": response.text[:200]},
            )


class SlackAlertProvider(AlertProvider):
    """Slack incoming webhook."""

    name = "slack"

    def __init__(self, webhook_url: str) -> None:
        self._url = webhook_url

    async def send(self, alert: HandoffAlert) -> None:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(self._url, json={"text": format_alert(alert)})
        except httpx.HTTPError as exc:
            raise ProviderError("Slack unreachable", code="slack_network_error") from exc
        if response.status_code != 200:
            raise ProviderError(
                "Slack rejected the alert", code="slack_rejected",
                details={"status": response.status_code, "body": response.text[:200]},
            )


def build_alert_provider() -> AlertProvider:
    """Create the provider chosen by ``HANDOFF_PROVIDER``."""
    s = get_settings()
    if s.handoff_provider == "telegram":
        return TelegramAlertProvider(s.telegram_bot_token.get_secret_value(), s.telegram_chat_id)
    if s.handoff_provider == "slack":
        return SlackAlertProvider(s.slack_webhook_url.get_secret_value())
    return MockAlertProvider()
