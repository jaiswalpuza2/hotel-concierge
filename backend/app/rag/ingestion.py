"""RAG ingestion pipeline orchestrator.

    load -> split -> embed -> store -> update status

Called as a FastAPI background task or from the ``ingest_kb`` CLI. Each stage that
the admin dashboard shows (``processing``, ``indexed``, ``failed``) is committed in
its own short transaction, so status changes are visible while the slow work (PDF
parsing, embedding) runs and no DB transaction stays open during it.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.repositories.document_repo import DocumentRepository
from app.exceptions import IngestionError
from app.rag.embedder import get_embedder
from app.rag.loaders import MarkdownLoader, PDFLoader
from app.rag.splitter import DevanagariAwareSplitter
from app.rag.vector_store import VectorStore

logger = structlog.get_logger(__name__)

_EMBED_BATCH_SIZE = 32
_MIME_BY_SUFFIX = {".pdf": "application/pdf", ".md": "text/markdown", ".markdown": "text/markdown", ".txt": "text/plain"}


def guess_mime_type(filename: str, declared: str | None = None) -> str:
    """Pick a supported MIME type, trusting the file extension over generic browser values."""
    by_suffix = _MIME_BY_SUFFIX.get(Path(filename).suffix.lower())
    base = (declared or "").split(";")[0].strip().lower()
    if base in ("application/pdf", "text/markdown", "text/plain"):
        return base
    return by_suffix or base or "application/octet-stream"


async def ingest_document(
    document_id: uuid.UUID,
    file_path: str,
    mime_type: str,
    session_factory: async_sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Run the full ingestion pipeline for one document.

    Status transitions: ``queued -> processing -> indexed`` or ``-> failed``.
    Never raises: failures are recorded on the document row for the dashboard.
    """
    logger.info("ingestion.started", document_id=str(document_id), mime_type=mime_type)

    try:
        async with session_factory() as session, session.begin():
            repo = DocumentRepository(session)
            document = await repo.get_by_id(document_id)
            display_name = document.original_name
            await repo.update_status(document_id, "processing")
    except Exception:
        logger.exception("ingestion.cannot_start", document_id=str(document_id))
        return

    try:
        raw_chunks = _load(file_path, mime_type)
        text_chunks = DevanagariAwareSplitter(chunk_size=512, overlap=64).split(raw_chunks)
        if not text_chunks:
            raise IngestionError(
                "Document produced no text chunks after splitting",
                code="empty_document",
                details={"document_id": str(document_id)},
            )
        for chunk in text_chunks:
            chunk.metadata["original_name"] = display_name

        embedder = get_embedder()
        embeddings: list[list[float]] = []
        for start in range(0, len(text_chunks), _EMBED_BATCH_SIZE):
            batch = text_chunks[start : start + _EMBED_BATCH_SIZE]
            embeddings.extend(await embedder.embed([c.text for c in batch]))
        bad = [len(v) for v in embeddings if len(v) != embedder.dimensions]
        if bad:
            raise IngestionError(
                f"Embedding size {bad[0]} does not match EMBEDDING_DIMENSIONS={embedder.dimensions}",
                code="embedding_dimension_mismatch",
            )

        async with session_factory() as session, session.begin():
            store = VectorStore(session)
            await store.delete_by_document_id(document_id)  # idempotent re-ingestion
            inserted = await store.insert_chunks(document_id, text_chunks, embeddings)
            await DocumentRepository(session).update_status(document_id, "indexed", chunk_count=inserted)
        logger.info("ingestion.complete", document_id=str(document_id), chunks_stored=inserted)

    except IngestionError as exc:
        await _mark_failed(session_factory, document_id, exc.message)
        logger.error("ingestion.failed", document_id=str(document_id), error_code=exc.code, error=exc.message)
    except Exception as exc:
        await _mark_failed(session_factory, document_id, f"Unexpected error during ingestion: {exc}")
        logger.exception("ingestion.unexpected_error", document_id=str(document_id))


async def _mark_failed(
    session_factory: async_sessionmaker,  # type: ignore[type-arg]
    document_id: uuid.UUID,
    message: str,
) -> None:
    try:
        async with session_factory() as session, session.begin():
            await DocumentRepository(session).update_status(
                document_id, "failed", error_message=message[:1000]
            )
    except Exception:
        logger.exception("ingestion.mark_failed_error", document_id=str(document_id))


def _load(file_path: str, mime_type: str) -> list:
    """Select and run the loader for ``mime_type``.

    Raises:
        IngestionError: If the MIME type is unsupported.
    """
    path = Path(file_path)
    if mime_type == "application/pdf":
        return PDFLoader().load(path)
    if mime_type in ("text/markdown", "text/plain"):
        return MarkdownLoader().load(path)
    raise IngestionError(
        f"Unsupported MIME type: {mime_type}",
        code="unsupported_mime_type",
        details={"mime_type": mime_type},
    )
