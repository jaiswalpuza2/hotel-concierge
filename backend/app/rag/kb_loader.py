"""Index the bundled sample knowledge base (``knowledge_base/en`` and ``/ne``)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.document import Document
from app.db.repositories.document_repo import DocumentRepository
from app.rag.ingestion import guess_mime_type, ingest_document

logger = structlog.get_logger(__name__)
_SUFFIXES = {".md", ".markdown", ".txt", ".pdf"}


async def ingest_folder(
    session_factory: async_sessionmaker[AsyncSession], root: Path
) -> dict[str, Any]:
    """Ingest every supported file under ``root`` that is not indexed yet.

    Idempotent: files whose display name already exists as an ``indexed`` or
    ``processing`` document are skipped; ``failed`` ones are retried.
    """
    summary: dict[str, Any] = {"ingested": [], "skipped": [], "failed": []}
    if not root.exists():
        logger.warning("kb.folder_missing", path=str(root))
        summary["error"] = f"Folder not found: {root}"
        return summary

    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in _SUFFIXES):
        name = path.name
        async with session_factory() as session, session.begin():
            existing = (
                await session.execute(select(Document).where(Document.original_name == name))
            ).scalars().first()
            if existing is not None and existing.status in ("indexed", "processing", "queued"):
                summary["skipped"].append(name)
                continue
            if existing is not None:
                document_id = existing.id
            else:
                doc = await DocumentRepository(session).create(
                    filename=str(path), original_name=name,
                    mime_type=guess_mime_type(name), size_bytes=path.stat().st_size,
                )
                document_id = doc.id
        await ingest_document(document_id, str(path), guess_mime_type(name), session_factory)
        async with session_factory() as session:
            status = (await session.execute(select(Document.status).where(Document.id == document_id))).scalar_one()
        (summary["ingested"] if status == "indexed" else summary["failed"]).append(name)
    logger.info("kb.ingest_folder_done", **{k: len(v) for k, v in summary.items() if isinstance(v, list)})
    return summary
