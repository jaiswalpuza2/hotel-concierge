"""Notification provider interfaces."""
from __future__ import annotations

from abc import ABC, abstractmethod


class SMSProvider(ABC):
    """Sends a text message."""

    name: str = "sms"

    @abstractmethod
    async def send(self, to: str, text: str) -> None:
        """Send ``text`` to a Nepali mobile number (10 digits). Raises ProviderError on failure."""


class EmailProvider(ABC):
    """Sends an email."""

    name: str = "email"

    @abstractmethod
    async def send(self, to: str, subject: str, body: str) -> None:
        """Send a plain-text email. Raises ProviderError on failure."""
