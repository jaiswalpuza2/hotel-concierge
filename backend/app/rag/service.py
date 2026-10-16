"""KnowledgeService -- the agents' entry point to the vector search."""
from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.rag.retriever import get_retriever

logger = structlog.get_logger(__name__)


class KnowledgeService:
    """Opens a short-lived session per search and returns plain dicts for the graph."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def search(self, query: str) -> list[dict[str, Any]]:
        """Return relevant chunks (above the confidence threshold), best first."""
        async with self._sessions() as session:
            chunks = await get_retriever(session).retrieve(query)
        return [
            {
                "document_id": c.document_id,
                "document_name": c.document_name,
                "section": c.section,
                "page_number": c.page_number,
                "content": c.content,
                "score": c.score,
            }
            for c in chunks
        ]
