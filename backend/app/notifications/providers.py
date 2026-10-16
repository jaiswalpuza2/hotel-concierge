"""SMS and email provider implementations (mock, Sparrow SMS, SMTP)."""
from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage

import httpx
import structlog

from app.config import get_settings
from app.exceptions import ProviderError
from app.notifications.base import EmailProvider, SMSProvider

logger = structlog.get_logger(__name__)


def _mask(value: str) -> str:
    return value[:3] + "***" + value[-3:] if len(value) > 6 else "***"


class MockSMSProvider(SMSProvider):
    """Records messages in memory and logs them; used in development and tests."""

    name = "mock-sms"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send(self, to: str, text: str) -> None:
        self.sent.append((to, text))
        logger.info("sms.mock_sent", to=_mask(to), chars=len(text))


class MockEmailProvider(EmailProvider):
    """Records emails in memory and logs them; used in development and tests."""

    name = "mock-email"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    async def send(self, to: str, subject: str, body: str) -> None:
        self.sent.append((to, subject, body))
        logger.info("email.mock_sent", to=_mask(to), subject=subject)


class SparrowSMSProvider(SMSProvider):
    """Sparrow SMS (Nepal) HTTP API. Docs: https://docs.sparrowsms.com"""

    name = "sparrow"
    _URL = "https://api.sparrowsms.com/v2/sms/"

    def __init__(self, token: str, sender: str) -> None:
        self._token = token
        self._sender = sender

    async def send(self, to: str, text: str) -> None:
        payload = {"token": self._token, "from": self._sender, "to": to, "text": text}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(self._URL, data=payload)
        except httpx.HTTPError as exc:
            raise ProviderError("Sparrow SMS unreachable", code="sms_network_error") from exc
        if response.status_code != 200:
            raise ProviderError(
                "Sparrow SMS rejected the message",
                code="sms_rejected",
                details={"status": response.status_code, "body": response.text[:200]},
            )


class SMTPEmailProvider(EmailProvider):
    """Plain SMTP with STARTTLS (works with Gmail app passwords, Mailgun, SES SMTP...)."""

    name = "smtp"

    def __init__(self, host: str, port: int, username: str, password: str, sender: str) -> None:
        self._host, self._port = host, port
        self._username, self._password, self._sender = username, password, sender

    def _send_blocking(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        with smtplib.SMTP(self._host, self._port, timeout=20) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if self._username:
                smtp.login(self._username, self._password)
            smtp.send_message(message)

    async def send(self, to: str, subject: str, body: str) -> None:
        try:
            await asyncio.to_thread(self._send_blocking, to, subject, body)
        except (smtplib.SMTPException, OSError) as exc:
            raise ProviderError(
                "SMTP delivery failed", code="email_failed", details={"error": exc.__class__.__name__}
            ) from exc


def build_sms_provider() -> SMSProvider:
    """Create the SMS provider chosen by ``SMS_PROVIDER``."""
    s = get_settings()
    if s.sms_provider == "sparrow":
        return SparrowSMSProvider(s.sms_sparrow_token.get_secret_value(), s.sms_sparrow_from)
    return MockSMSProvider()


def build_email_provider() -> EmailProvider:
    """Create the email provider chosen by ``EMAIL_PROVIDER``."""
    s = get_settings()
    if s.email_provider == "smtp":
        return SMTPEmailProvider(
            s.smtp_host, s.smtp_port, s.smtp_username, s.smtp_password.get_secret_value(), s.smtp_from
        )
    return MockEmailProvider()
