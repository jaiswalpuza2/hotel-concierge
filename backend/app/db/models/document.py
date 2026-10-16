"""Document and DocumentChunk ORM models for the RAG knowledge base."""
from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

DocumentStatus = Literal["queued", "processing", "indexed", "failed"]


class Document(Base):
    """A knowledge-base document uploaded by an admin.

    Tracks ingestion lifecycle: queued → processing → indexed (or failed).
    When deleted, cascade deletes all associated ``DocumentChunk`` rows
    (and their pgvector embeddings via ON DELETE CASCADE on the FK).
    """

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Name used on disk / in object storage
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # Original file name as uploaded by the admin
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        String(20), nullable=False, default="queued"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uploaded_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    indexed_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    chunks: Mapped[list[DocumentChunk]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Document {self.original_name!r} status={self.status!r}>"


class DocumentChunk(Base):
    """A text chunk from a document, stored with its vector embedding.

    The ``embedding`` column uses the ``pgvector`` ``VECTOR`` type.
    The HNSW index is created in the Alembic migration (not here, because
    SQLAlchemy's ``Index`` does not support the pgvector operator classes
    without a raw DDL statement).
    """

    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # embedding column added via pgvector in the Alembic migration
    # (declared here as Text placeholder; migration overwrites with VECTOR type)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        Index("idx_chunks_document", "document_id"),
        # The HNSW vector index is added as raw DDL in the migration:
        # CREATE INDEX idx_chunks_embedding ON document_chunks
        #   USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64);
    )

    # Relationships
    document: Mapped[Document] = relationship("Document", back_populates="chunks")

    def __repr__(self) -> str:
        return (
            f"<DocumentChunk doc={str(self.document_id)[:8]}… "
            f"idx={self.chunk_index}>"
        )
