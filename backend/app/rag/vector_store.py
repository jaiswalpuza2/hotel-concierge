"""pgvector store — insert and similarity-search document chunk embeddings.

All SQL uses parameterised queries via SQLAlchemy ``text()`` to prevent
injection. The HNSW index on ``document_chunks.embedding`` (created in the
Alembic migration) makes cosine similarity search fast.
"""
from __future__ import annotations

import json
import uuid

import structlog
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.document import DocumentChunk
from app.rag.splitter import TextChunk

logger = structlog.get_logger(__name__)


class VectorStore:
    """Async pgvector operations for document chunks.

    Args:
        session: An active SQLAlchemy async session.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_chunks(
        self,
        document_id: uuid.UUID,
        chunks: list[TextChunk],
        embeddings: list[list[float]],
    ) -> int:
        """Insert document chunks with their embeddings into pgvector.

        Args:
            document_id: The UUID of the parent Document record.
            chunks: TextChunks from the splitter (text + metadata).
            embeddings: One embedding vector per chunk, in the same order.

        Returns:
            Number of rows inserted.

        Raises:
            ValueError: If chunks and embeddings lengths differ.
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"chunks ({len(chunks)}) and embeddings ({len(embeddings)}) "
                "must have the same length"
            )

        if not chunks:
            return 0

        rows_inserted = 0
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            chunk_id = uuid.uuid4()
            metadata = {
                **chunk.metadata,
                "section": chunk.section,
                "document_id": str(document_id),
            }
            # Use raw SQL for the pgvector INSERT because SQLAlchemy's ORM
            # does not know the VECTOR type. The vector is cast via the
            # pgvector extension's ::vector cast syntax.
            await self._session.execute(
                text(
                    "INSERT INTO document_chunks "
                    "(id, document_id, chunk_index, content, embedding, metadata, page_number) "
                    "VALUES "
                    "(:id, :doc_id, :idx, :content, CAST(CAST(:embedding AS text) AS vector), CAST(:metadata AS jsonb), :page)"
                ),
                {
                    "id": str(chunk_id),
                    "doc_id": str(document_id),
                    "idx": chunk.chunk_index,
                    "content": chunk.text,
                    "embedding": "[" + ",".join(f"{x:.7f}" for x in embedding) + "]",
                    "metadata": json.dumps(metadata, ensure_ascii=False),
                    "page": chunk.page_number,
                },
            )
            rows_inserted += 1

        await self._session.flush()
        logger.info(
            "vector_store.chunks_inserted",
            document_id=str(document_id),
            count=rows_inserted,
        )
        return rows_inserted

    async def delete_by_document_id(self, document_id: uuid.UUID) -> int:
        """Delete all chunks belonging to a document.

        Args:
            document_id: The document whose chunks to remove.

        Returns:
            Number of rows deleted.
        """
        result = await self._session.execute(
            delete(DocumentChunk).where(
                DocumentChunk.document_id == document_id
            )
        )
        count = result.rowcount
        await self._session.flush()
        logger.info(
            "vector_store.chunks_deleted",
            document_id=str(document_id),
            count=count,
        )
        return count

    async def similarity_search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        document_id: uuid.UUID | None = None,
    ) -> list[dict]:
        """Find the top-k most similar chunks using cosine distance.

        Args:
            query_embedding: The embedded query vector.
            top_k: Number of results to return.
            document_id: Optional filter to a single document.

        Returns:
            List of dicts with keys: id, document_id, chunk_index, content,
            score (cosine similarity 0–1), metadata, page_number.
        """
        embedding_str = "[" + ",".join(f"{x:.7f}" for x in query_embedding) + "]"

        if document_id is not None:
            sql = text(
                "SELECT id, document_id, chunk_index, content, metadata, page_number, "
                "1 - (embedding <=> CAST(CAST(:query AS text) AS vector)) AS score "
                "FROM document_chunks "
                "WHERE document_id = :doc_id "
                "ORDER BY embedding <=> CAST(CAST(:query AS text) AS vector) "
                "LIMIT :k"
            )
            params = {"query": embedding_str, "doc_id": str(document_id), "k": top_k}
        else:
            sql = text(
                "SELECT id, document_id, chunk_index, content, metadata, page_number, "
                "1 - (embedding <=> CAST(CAST(:query AS text) AS vector)) AS score "
                "FROM document_chunks "
                "ORDER BY embedding <=> CAST(CAST(:query AS text) AS vector) "
                "LIMIT :k"
            )
            params = {"query": embedding_str, "k": top_k}

        result = await self._session.execute(sql, params)
        rows = result.mappings().all()

        chunks = []
        for row in rows:
            meta = row["metadata"]
            if isinstance(meta, str):
                meta = json.loads(meta)
            chunks.append(
                {
                    "id": str(row["id"]),
                    "document_id": str(row["document_id"]),
                    "chunk_index": row["chunk_index"],
                    "content": row["content"],
                    "score": float(row["score"]),
                    "metadata": meta,
                    "page_number": row["page_number"],
                }
            )

        logger.debug(
            "vector_store.similarity_search",
            top_k=top_k,
            result_count=len(chunks),
            top_score=chunks[0]["score"] if chunks else None,
        )
        return chunks
