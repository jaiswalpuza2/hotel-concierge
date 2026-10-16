"""RAG retriever — top-k similarity search with optional reranking.

The retriever is the read path of the RAG pipeline:
1. Embed the user's query using the same model used at ingestion time.
2. Run cosine similarity search against pgvector.
3. Filter out chunks below the confidence threshold.
4. Optionally rerank using a cross-encoder.
5. Return ``RetrievedChunk`` objects that the RAG agent attaches to responses.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.embedder import get_embedder
from app.rag.vector_store import VectorStore

logger = structlog.get_logger(__name__)


@dataclass
class RetrievedChunk:
    """A retrieved document chunk returned to the agent.

    Attributes:
        document_id: UUID string of the parent document.
        document_name: Human-readable document name (from metadata or filename).
        chunk_index: Position within the document (0-based).
        content: The chunk text.
        score: Cosine similarity score (0.0–1.0). Higher is more similar.
        page_number: For PDFs; None for Markdown.
        section: Nearest Markdown heading; None for PDFs.
        metadata: All other metadata from the chunk.
    """

    document_id: str
    document_name: str
    chunk_index: int
    content: str
    score: float
    page_number: int | None = None
    section: str | None = None
    metadata: dict = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}


# ---------------------------------------------------------------------------
# Reranker interface
# ---------------------------------------------------------------------------


class RerankerProvider(ABC):
    """Abstract base class for cross-encoder rerankers.

    A reranker takes a query and a list of candidate chunks, then
    re-scores each chunk with a more expensive but more accurate model.
    """

    @abstractmethod
    async def rerank(
        self, query: str, chunks: list[RetrievedChunk]
    ) -> list[RetrievedChunk]:
        """Rerank chunks by relevance to the query.

        Args:
            query: The user's original query text.
            chunks: Candidates from the initial similarity search.

        Returns:
            Chunks sorted by cross-encoder score descending (most relevant first).
        """


class CrossEncoderReranker(RerankerProvider):
    """Cross-encoder reranker using sentence-transformers.

    Default model: ``cross-encoder/ms-marco-MiniLM-L-6-v2``
    """

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model: Any = None

    def _load_model(self) -> None:
        if self._model is not None:
            return
        from sentence_transformers import CrossEncoder  # type: ignore[import]
        logger.info("reranker.loading_model", model=self._model_name)
        self._model = CrossEncoder(self._model_name)
        logger.info("reranker.model_loaded", model=self._model_name)

    async def rerank(
        self, query: str, chunks: list[RetrievedChunk]
    ) -> list[RetrievedChunk]:
        """Rerank using the cross-encoder; falls back to original order on error."""
        import asyncio

        if not chunks:
            return chunks

        try:
            self._load_model()
        except Exception as exc:
            logger.warning(
                "reranker.model_load_failed",
                error=str(exc),
                fallback="returning original order",
            )
            return chunks

        pairs = [[query, c.content] for c in chunks]

        def _score() -> list[float]:
            assert self._model is not None
            return self._model.predict(pairs).tolist()

        scores = await asyncio.to_thread(_score)
        for chunk, score in zip(chunks, scores, strict=True):
            chunk.score = float(score)

        return sorted(chunks, key=lambda c: c.score, reverse=True)


# ---------------------------------------------------------------------------
# Retriever
# ---------------------------------------------------------------------------


class Retriever:
    """Run similarity search and return filtered, optionally reranked chunks.

    Args:
        session: Active SQLAlchemy async session.
        top_k: Number of results to request from pgvector.
        threshold: Minimum cosine similarity score to include in results.
        reranker: Optional reranker; if None, results are returned in
            similarity order.
    """

    def __init__(
        self,
        session: AsyncSession,
        top_k: int = 5,
        threshold: float = 0.6,
        reranker: RerankerProvider | None = None,
    ) -> None:
        self._session = session
        self._top_k = top_k
        self._threshold = threshold
        self._reranker = reranker
        self._vector_store = VectorStore(session)

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        threshold: float | None = None,
    ) -> list[RetrievedChunk]:
        """Embed the query, search pgvector, filter, optionally rerank.

        Args:
            query: The user's question or search phrase.
            top_k: Override the instance-level top_k for this call.
            threshold: Override the instance-level threshold for this call.

        Returns:
            List of RetrievedChunks above the threshold, sorted by score desc.
            Returns an empty list if no relevant chunks are found.
        """
        k = top_k or self._top_k
        t = threshold if threshold is not None else self._threshold

        # 1. Embed the query
        embedder = get_embedder()
        query_vector = await embedder.embed_query(query)

        # 2. Similarity search
        raw_results = await self._vector_store.similarity_search(
            query_embedding=query_vector,
            top_k=k * 2,  # over-fetch to allow threshold filtering
        )

        # 3. Map raw DB rows to RetrievedChunk and filter by threshold
        chunks: list[RetrievedChunk] = []
        for row in raw_results:
            if row["score"] < t:
                continue
            meta = row.get("metadata", {}) or {}
            chunks.append(
                RetrievedChunk(
                    document_id=row["document_id"],
                    document_name=meta.get("original_name", meta.get("filename", "Unknown")),
                    chunk_index=row["chunk_index"],
                    content=row["content"],
                    score=row["score"],
                    page_number=row.get("page_number"),
                    section=meta.get("section"),
                    metadata=meta,
                )
            )

        # Trim to requested top_k after threshold filter
        chunks = chunks[:k]

        # 4. Optional reranking
        if self._reranker and chunks:
            chunks = await self._reranker.rerank(query, chunks)

        logger.info(
            "retriever.retrieved",
            query_preview=query[:50],
            top_k=k,
            threshold=t,
            result_count=len(chunks),
            top_score=chunks[0].score if chunks else None,
        )
        return chunks


@lru_cache(maxsize=1)
def _get_reranker() -> RerankerProvider | None:
    """Return configured reranker or None if disabled."""
    from app.config import get_settings
    settings = get_settings()
    if not settings.reranker_enabled:
        return None
    return CrossEncoderReranker(settings.reranker_model)


def get_retriever(session: AsyncSession) -> Retriever:
    """Factory for the configured Retriever instance.

    Args:
        session: The active DB session for the current request.

    Returns:
        A Retriever ready to call ``retrieve()``.
    """
    from app.config import get_settings
    settings = get_settings()
    return Retriever(
        session=session,
        top_k=settings.retrieval_top_k,
        threshold=settings.retrieval_confidence_threshold,
        reranker=_get_reranker(),
    )
