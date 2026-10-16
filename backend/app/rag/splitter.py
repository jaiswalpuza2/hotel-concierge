"""Devanagari-aware recursive character text splitter.

Splits text into chunks of approximately ``chunk_size`` characters with
``overlap`` character overlap between consecutive chunks.

Sentence boundary detection handles:
- Devanagari danda (।) and double danda (॥)
- Standard punctuation: . ! ?
- Paragraph breaks (double newline)
- Single newlines (lower priority)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import ClassVar

import structlog

from app.rag.loaders import RawChunk

logger = structlog.get_logger(__name__)


@dataclass
class TextChunk:
    """A text chunk ready for embedding.

    Attributes:
        text: The chunk content (stripped).
        chunk_index: 0-based index within the document.
        page_number: From the source RawChunk (None for Markdown).
        section: Nearest heading from the source RawChunk.
        metadata: Carries forward all metadata from the source RawChunk.
    """

    text: str
    chunk_index: int
    page_number: int | None = None
    section: str | None = None
    metadata: dict = field(default_factory=dict)


class DevanagariAwareSplitter:
    """Recursive character splitter that respects Devanagari sentence boundaries.

    Split priority (highest to lowest):
    1. Double newline (paragraph boundary)
    2. Devanagari danda (।) or double danda (॥)
    3. Standard sentence endings: . ? !
    4. Semicolon or colon
    5. Single newline
    6. Space (last resort — split mid-sentence only if necessary)

    Args:
        chunk_size: Target maximum characters per chunk (default 512).
        overlap: Characters of overlap between consecutive chunks (default 64).
        min_chunk_size: Discard chunks shorter than this (default 20).
    """

    # Ordered list of split patterns (highest priority first)
    _SEPARATORS: ClassVar[list[str]] = [
        r"\n\n",          # paragraph break
        r"[।॥]",          # Devanagari danda
        r"[.!?]\s",       # sentence-ending punctuation + space
        r"[;:]\s",        # clause boundary
        r"\n",            # line break
        r"\s",            # word boundary (last resort)
    ]

    def __init__(
        self,
        chunk_size: int = 512,
        overlap: int = 64,
        min_chunk_size: int = 20,
    ) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.min_chunk_size = min_chunk_size

    def split(self, raw_chunks: list[RawChunk]) -> list[TextChunk]:
        """Split a list of RawChunks into TextChunks for embedding.

        Args:
            raw_chunks: Output of a document loader.

        Returns:
            List of TextChunks with incrementing chunk_index.
        """
        text_chunks: list[TextChunk] = []
        global_index = 0

        for raw in raw_chunks:
            splits = self._split_text(raw.text)
            for text in splits:
                if len(text.strip()) < self.min_chunk_size:
                    continue
                text_chunks.append(
                    TextChunk(
                        text=text.strip(),
                        chunk_index=global_index,
                        page_number=raw.page_number,
                        section=raw.section,
                        metadata=dict(raw.metadata),
                    )
                )
                global_index += 1

        logger.debug(
            "splitter.split",
            raw_chunk_count=len(raw_chunks),
            text_chunk_count=len(text_chunks),
            chunk_size=self.chunk_size,
            overlap=self.overlap,
        )
        return text_chunks

    def _split_text(self, text: str) -> list[str]:
        """Recursively split text into chunks of at most chunk_size characters."""
        if len(text) <= self.chunk_size:
            return [text] if text.strip() else []

        # Try each separator in priority order
        for separator in self._SEPARATORS:
            parts = re.split(separator, text)
            if len(parts) > 1:
                return self._merge_splits(parts, separator)

        # No separator found — hard-split at chunk_size
        return self._hard_split(text)

    def _merge_splits(self, parts: list[str], separator: str) -> list[str]:
        """Merge small parts back together until they reach chunk_size.

        This prevents producing dozens of tiny chunks when text has many
        short sentences.
        """
        merged: list[str] = []
        current = ""

        for part in parts:
            candidate = current + (" " if current else "") + part
            if len(candidate) <= self.chunk_size:
                current = candidate
            else:
                if current:
                    merged.append(current)
                # If the part itself is too large, recursively split it
                if len(part) > self.chunk_size:
                    sub_chunks = self._split_text(part)
                    if sub_chunks:
                        # Start next current with overlap from last sub-chunk
                        last = sub_chunks[-1]
                        merged.extend(sub_chunks[:-1])
                        current = last[-self.overlap:] if len(last) > self.overlap else last
                    else:
                        current = ""
                else:
                    current = part

        if current:
            merged.append(current)

        # Add overlap: each chunk starts with the tail of the previous
        return self._add_overlap(merged)

    def _add_overlap(self, chunks: list[str]) -> list[str]:
        """Prepend overlap text from the previous chunk."""
        if self.overlap == 0 or len(chunks) <= 1:
            return chunks
        result: list[str] = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_tail = chunks[i - 1][-self.overlap:]
            result.append(prev_tail + " " + chunks[i])
        return result

    def _hard_split(self, text: str) -> list[str]:
        """Split text into fixed-size chunks when no separator works."""
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            chunks.append(text[start:end])
            start = end - self.overlap if end - self.overlap > start else end
        return chunks
