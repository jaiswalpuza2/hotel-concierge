"""Document loaders for PDF and Markdown files.

Each loader returns a list of ``RawChunk`` objects — text segments with
page/section metadata attached before splitting occurs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class RawChunk:
    """A raw text segment extracted from a document before splitting.

    Attributes:
        text: The extracted text content.
        page_number: 1-based page number (PDF) or None (Markdown).
        section: The nearest heading above this chunk (Markdown only).
        metadata: Extra key-value pairs propagated to DocumentChunk.metadata_.
    """

    text: str
    page_number: int | None = None
    section: str | None = None
    metadata: dict = field(default_factory=dict)


class PDFLoader:
    """Load a PDF file and return one RawChunk per page.

    Uses PyMuPDF (``fitz``) which handles complex PDFs including Devanagari
    text better than most pure-Python alternatives.
    """

    def load(self, path: str | Path) -> list[RawChunk]:
        """Extract text from every page of the PDF.

        Args:
            path: Path to the PDF file.

        Returns:
            List of RawChunks, one per page (skipping blank pages).

        Raises:
            IngestionError: If the file cannot be opened or parsed.
        """
        import fitz  # PyMuPDF

        from app.exceptions import IngestionError

        file_path = Path(path)
        if not file_path.exists():
            raise IngestionError(
                f"PDF file not found: {file_path}",
                code="file_not_found",
                details={"path": str(file_path)},
            )

        try:
            doc = fitz.open(str(file_path))
        except Exception as exc:
            raise IngestionError(
                f"Failed to open PDF: {file_path.name}",
                code="pdf_open_error",
                details={"error": str(exc)},
            ) from exc

        chunks: list[RawChunk] = []
        for page_num in range(len(doc)):
            try:
                page = doc[page_num]
                text = page.get_text("text")
                # Skip effectively blank pages
                if len(text.strip()) < 20:
                    continue
                chunks.append(
                    RawChunk(
                        text=text,
                        page_number=page_num + 1,
                        metadata={"source_format": "pdf"},
                    )
                )
            except Exception as exc:
                logger.warning(
                    "pdf.page_extraction_error",
                    page=page_num + 1,
                    error=str(exc),
                )
                continue

        page_count = len(doc)
        doc.close()
        logger.info(
            "pdf.loaded",
            filename=file_path.name,
            page_count=page_count,
            chunk_count=len(chunks),
        )
        return chunks


class MarkdownLoader:
    """Load a Markdown file and return one RawChunk per section.

    Sections are split on heading lines (``# ``, ``## ``, ``### ``).
    Each chunk carries the nearest heading as ``section`` metadata.
    """

    # Heading pattern — matches # / ## / ### at line start
    _HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)

    def load(self, path: str | Path) -> list[RawChunk]:
        """Split a Markdown file into per-section RawChunks.

        Args:
            path: Path to the .md file.

        Returns:
            List of RawChunks, one per section (or one chunk if no headings).

        Raises:
            IngestionError: If the file cannot be read.
        """
        from app.exceptions import IngestionError

        file_path = Path(path)
        if not file_path.exists():
            raise IngestionError(
                f"Markdown file not found: {file_path}",
                code="file_not_found",
                details={"path": str(file_path)},
            )

        try:
            text = file_path.read_text(encoding="utf-8")
        except Exception as exc:
            raise IngestionError(
                f"Failed to read Markdown file: {file_path.name}",
                code="markdown_read_error",
                details={"error": str(exc)},
            ) from exc

        chunks = self._split_by_headings(text)

        logger.info(
            "markdown.loaded",
            filename=file_path.name,
            chunk_count=len(chunks),
        )
        return chunks

    def _split_by_headings(self, text: str) -> list[RawChunk]:
        """Split Markdown text on heading boundaries."""
        # Find all heading positions
        heading_matches = list(self._HEADING_RE.finditer(text))

        if not heading_matches:
            # No headings — return the whole file as one chunk
            stripped = text.strip()
            if stripped:
                return [RawChunk(text=stripped, metadata={"source_format": "markdown"})]
            return []

        chunks: list[RawChunk] = []
        positions = [(m.start(), m.group(2).strip()) for m in heading_matches]

        for i, (start, section_title) in enumerate(positions):
            end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
            section_text = text[start:end].strip()
            if len(section_text) < 10:
                continue
            chunks.append(
                RawChunk(
                    text=section_text,
                    section=section_title,
                    metadata={"source_format": "markdown"},
                )
            )

        return chunks
