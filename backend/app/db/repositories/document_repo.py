"""DocumentRepository — async DB operations for document ingestion lifecycle."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.document import Document, DocumentChunk
from app.exceptions import NotFoundError

logger = structlog.get_logger(__name__)

DocumentStatus = Literal["queued", "processing", "indexed", "failed"]


class DocumentRepository:
    """Async DB operations for Document and DocumentChunk records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        filename: str,
        original_name: str,
        mime_type: str,
        size_bytes: int,
    ) -> Document:
        """Create a new Document record with status='queued'.

        Returns:
            The newly created Document with its UUID assigned.
        """
        doc = Document(
            filename=filename,
            original_name=original_name,
            mime_type=mime_type,
            size_bytes=size_bytes,
            status="queued",
        )
        self._session.add(doc)
        await self._session.flush()
        logger.info("document.created", document_id=str(doc.id), original_name=original_name)
        return doc

    async def get_by_id(self, document_id: uuid.UUID) -> Document:
        """Fetch a document by primary key.

        Raises:
            NotFoundError: If no document with that ID exists.
        """
        result = await self._session.execute(
            select(Document).where(Document.id == document_id)
        )
        doc = result.scalar_one_or_none()
        if doc is None:
            raise NotFoundError(
                "Document not found",
                code="document_not_found",
                details={"document_id": str(document_id)},
            )
        return doc

    async def update_status(
        self,
        document_id: uuid.UUID,
        status: DocumentStatus,
        *,
        error_message: str | None = None,
        chunk_count: int | None = None,
    ) -> None:
        """Update the ingestion status of a document.

        Args:
            document_id: The document's UUID.
            status: New status value.
            error_message: Set when status='failed'.
            chunk_count: Set when status='indexed'.
        """
        doc = await self.get_by_id(document_id)
        doc.status = status
        if error_message is not None:
            doc.error_message = error_message
        if chunk_count is not None:
            doc.chunk_count = chunk_count
        if status == "indexed":
            doc.indexed_at = datetime.now(tz=UTC)
        await self._session.flush()
        logger.info(
            "document.status_updated",
            document_id=str(document_id),
            status=status,
            chunk_count=chunk_count,
        )

    async def list_all(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Document], int]:
        """Return paginated list of documents, newest first.

        Returns:
            Tuple of (items, total_count).
        """
        count_result = await self._session.execute(select(Document.id))
        total = len(count_result.all())

        offset = (page - 1) * page_size
        result = await self._session.execute(
            select(Document)
            .order_by(Document.uploaded_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    async def delete_with_chunks(self, document_id: uuid.UUID) -> None:
        """Delete a document and all its vector chunks.

        The ON DELETE CASCADE FK on ``document_chunks.document_id`` means
        the DB removes chunks automatically when the Document row is deleted.
        We also explicitly delete chunks first to give pgvector a chance to
        clean up index entries within the same transaction.

        Raises:
            NotFoundError: If no document with that ID exists.
        """
        # Verify existence first (raises NotFoundError if missing)
        await self.get_by_id(document_id)

        # Delete chunks (CASCADE would handle this, but explicit is safer)
        await self._session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        await self._session.execute(
            delete(Document).where(Document.id == document_id)
        )
        await self._session.flush()
        logger.info("document.deleted", document_id=str(document_id))
