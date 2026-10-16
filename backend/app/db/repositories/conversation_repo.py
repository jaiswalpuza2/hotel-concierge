"""ConversationRepository -- chat sessions and messages."""
from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.conversation import Conversation, Message
from app.exceptions import NotFoundError

logger = structlog.get_logger(__name__)


class ConversationRepository:
    """Async DB operations for Conversation and Message records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, session_id: uuid.UUID, language: str = "en") -> Conversation:
        """Return the conversation for a session id, creating it on first use."""
        result = await self._session.execute(
            select(Conversation).where(Conversation.session_id == session_id)
        )
        conversation = result.scalar_one_or_none()
        if conversation is None:
            conversation = Conversation(session_id=session_id, detected_language=language)
            self._session.add(conversation)
            await self._session.flush()
            logger.info("conversation.created", session_id=str(session_id))
        return conversation

    async def get_by_id(self, conversation_id: uuid.UUID) -> Conversation:
        """Fetch a conversation with its messages.

        Raises:
            NotFoundError: Unknown conversation.
        """
        result = await self._session.execute(
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .options(selectinload(Conversation.messages))
        )
        conversation = result.scalar_one_or_none()
        if conversation is None:
            raise NotFoundError(
                "Conversation not found",
                code="conversation_not_found",
                details={"conversation_id": str(conversation_id)},
            )
        return conversation

    async def add_message(
        self,
        conversation_id: uuid.UUID,
        *,
        role: str,
        content: str,
        intent: str | None = None,
        confidence: float | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        retrieved_chunks: list[dict[str, Any]] | None = None,
    ) -> Message:
        """Append a message to a conversation."""
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            intent=intent,
            confidence=confidence,
            tool_calls=tool_calls or [],
            retrieved_chunks=retrieved_chunks or [],
        )
        self._session.add(message)
        await self._session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(last_active_at=func.now())
        )
        await self._session.flush()
        return message

    async def set_status(self, conversation_id: uuid.UUID, status: str) -> None:
        """Update a conversation's status (active | handed_off | resolved | abandoned)."""
        conversation = await self.get_by_id(conversation_id)
        conversation.status = status
        await self._session.flush()

    async def set_language(self, conversation_id: uuid.UUID, language: str) -> None:
        """Record the detected language."""
        result = await self._session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conversation = result.scalar_one_or_none()
        if conversation is not None and conversation.detected_language != language:
            conversation.detected_language = language
            await self._session.flush()

    async def recent_messages(self, conversation_id: uuid.UUID, limit: int = 12) -> list[Message]:
        """Return the latest ``limit`` messages in chronological order."""
        result = await self._session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    async def list_all(
        self, *, page: int = 1, page_size: int = 20, status: str | None = None
    ) -> tuple[list[Conversation], int]:
        """Paginated conversations, most recently active first."""
        base = select(Conversation)
        count = select(func.count(Conversation.id))
        if status:
            base = base.where(Conversation.status == status)
            count = count.where(Conversation.status == status)
        total = (await self._session.execute(count)).scalar_one()
        result = await self._session.execute(
            base.order_by(Conversation.last_active_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(total)
