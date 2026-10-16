"""Document management endpoints.

POST   /api/v1/documents              -- upload and queue ingestion
GET    /api/v1/documents              -- list all documents with status
DELETE /api/v1/documents/{id}         -- delete document and its vectors

All endpoints require authentication. Deletion requires the admin role.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.base import async_session_factory, get_db_session
from app.db.models.user import User
from app.db.repositories.document_repo import DocumentRepository
from app.dependencies import get_current_user, require_role
from app.exceptions import ValidationError
from app.rag.ingestion import guess_mime_type, ingest_document

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["documents"])

# Allowlisted MIME types for upload
_ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    {"application/pdf", "text/markdown", "text/plain"}
)

# Where uploaded files are stored temporarily before ingestion
_UPLOAD_DIR = Path("uploads")


def _get_upload_dir() -> Path:
    """Return (and create if needed) the upload directory."""
    _UPLOAD_DIR.mkdir(exist_ok=True, parents=True)
    return _UPLOAD_DIR


@router.post(
    "",
    status_code=201,
    summary="Upload a document and queue it for ingestion",
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    language: str = Form(default="en"),
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
    _user: User = Depends(get_current_user),  # noqa: B008
) -> JSONResponse:
    """Upload a PDF or Markdown document and queue it for RAG ingestion.

    The file is saved to disk and a DB record is created immediately
    (status=queued). The actual ingestion (split → embed → store) runs
    as a background task so the response is instant.

    Raises:
        ValidationError: If the MIME type is not allowed or the file exceeds the size limit.
    """
    settings = get_settings()

    # Validate MIME type — use Content-Type from upload, with fallback detection
    content_type = file.content_type or "application/octet-stream"
    # Browsers often label .md files 'application/octet-stream' or 'text/x-markdown';
    # trust the extension when the declared type is generic.
    mime_base = guess_mime_type(file.filename or "", content_type)

    if mime_base not in _ALLOWED_MIME_TYPES:
        raise ValidationError(
            f"File type '{mime_base}' is not supported. "
            "Allowed: PDF, Markdown (.md), plain text (.txt).",
            code="unsupported_file_type",
            details={"content_type": content_type},
        )

    # Read the file content to check size
    content = await file.read()
    size_bytes = len(content)

    if size_bytes > settings.max_file_upload_bytes:
        max_mb = settings.max_file_upload_bytes // (1024 * 1024)
        raise ValidationError(
            f"File exceeds the maximum upload size of {max_mb} MB.",
            code="file_too_large",
            details={"size_bytes": size_bytes, "max_bytes": settings.max_file_upload_bytes},
        )

    if size_bytes == 0:
        raise ValidationError("Uploaded file is empty.", code="empty_file")

    # Persist file to disk
    upload_dir = _get_upload_dir()
    file_id = uuid.uuid4()
    suffix = Path(file.filename or "upload").suffix or ".bin"
    stored_filename = f"{file_id}{suffix}"
    stored_path = upload_dir / stored_filename

    stored_path.write_bytes(content)

    # Create the DB record
    doc_repo = DocumentRepository(session)
    document = await doc_repo.create(
        filename=stored_filename,
        original_name=file.filename or stored_filename,
        mime_type=mime_base,
        size_bytes=size_bytes,
    )
    await session.commit()

    # Queue background ingestion (fires after response is sent)
    background_tasks.add_task(
        ingest_document,
        document_id=document.id,
        file_path=str(stored_path),
        mime_type=mime_base,
        session_factory=async_session_factory,
    )

    logger.info(
        "document.upload_accepted",
        document_id=str(document.id),
        filename=document.original_name,
        size_bytes=size_bytes,
        language=language,
    )

    return JSONResponse(
        status_code=201,
        content={
            "id": str(document.id),
            "original_name": document.original_name,
            "mime_type": document.mime_type,
            "size_bytes": document.size_bytes,
            "status": document.status,
            "uploaded_at": document.uploaded_at.isoformat(),
        },
    )


@router.get(
    "",
    summary="List all documents with their ingestion status",
)
async def list_documents(
    page: int = 1,
    page_size: int = 20,
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
    _user: User = Depends(get_current_user),  # noqa: B008
) -> JSONResponse:
    """Return a paginated list of all uploaded documents."""
    doc_repo = DocumentRepository(session)
    docs, total = await doc_repo.list_all(page=page, page_size=page_size)

    items = [
        {
            "id": str(d.id),
            "original_name": d.original_name,
            "mime_type": d.mime_type,
            "size_bytes": d.size_bytes,
            "status": d.status,
            "chunk_count": d.chunk_count,
            "error_message": d.error_message,
            "uploaded_at": d.uploaded_at.isoformat(),
            "indexed_at": d.indexed_at.isoformat() if d.indexed_at else None,
        }
        for d in docs
    ]

    return JSONResponse(
        content={
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.delete(
    "/{document_id}",
    status_code=204,
    response_class=Response,
    summary="Delete a document and all its vectors",
)
async def delete_document(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
    _user: User = Depends(require_role("admin")),  # noqa: B008
) -> Response:
    """Delete a document record and all associated pgvector chunks.

    Also removes the uploaded file from disk.

    Raises:
        NotFoundError: If the document does not exist.
    """
    doc_repo = DocumentRepository(session)

    # Fetch first to get the filename before deleting
    doc = await doc_repo.get_by_id(document_id)
    stored_path = _get_upload_dir() / doc.filename

    await doc_repo.delete_with_chunks(document_id)
    await session.commit()

    # Best-effort cleanup of the file on disk
    try:
        if stored_path.exists():
            stored_path.unlink()
    except OSError as exc:
        logger.warning(
            "document.file_delete_failed",
            document_id=str(document_id),
            path=str(stored_path),
            error=str(exc),
        )

    logger.info("document.deleted", document_id=str(document_id))
    return Response(status_code=204)
