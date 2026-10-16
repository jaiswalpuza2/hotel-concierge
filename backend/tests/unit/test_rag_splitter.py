"""Unit tests for the Devanagari-aware recursive text splitter."""
from __future__ import annotations

from app.rag.loaders import RawChunk
from app.rag.splitter import DevanagariAwareSplitter


def _splitter(chunk_size: int = 200, overlap: int = 20) -> DevanagariAwareSplitter:
    return DevanagariAwareSplitter(chunk_size=chunk_size, overlap=overlap, min_chunk_size=5)


class TestDevanagariAwareSplitter:
    def test_short_text_is_single_chunk(self) -> None:
        s = _splitter()
        raw = [RawChunk(text="Hello world. This is short.")]
        chunks = s.split(raw)
        assert len(chunks) == 1
        assert "Hello world" in chunks[0].text

    def test_splits_on_devanagari_danda(self) -> None:
        s = _splitter(chunk_size=50)
        # Each sentence is < 50 chars individually; total > 50
        text = "यो होटेल राम्रो छ।" * 5  # ~95 chars
        raw = [RawChunk(text=text)]
        chunks = s.split(raw)
        assert len(chunks) >= 2
        # No chunk should exceed chunk_size significantly
        for c in chunks:
            assert len(c.text) <= 200  # loose bound after overlap

    def test_splits_on_paragraph_break(self) -> None:
        s = _splitter(chunk_size=100)
        text = ("A" * 90) + "\n\n" + ("B" * 90)
        raw = [RawChunk(text=text)]
        chunks = s.split(raw)
        assert len(chunks) >= 2

    def test_overlap_prepended_to_next_chunk(self) -> None:
        s = DevanagariAwareSplitter(chunk_size=80, overlap=20, min_chunk_size=5)
        text = ("word " * 30)  # 150 chars
        raw = [RawChunk(text=text.strip())]
        chunks = s.split(raw)
        assert len(chunks) >= 2
        # Second chunk should start with the tail of the first
        tail_of_first = chunks[0].text[-20:]
        assert tail_of_first.strip() in chunks[1].text

    def test_chunk_index_is_sequential(self) -> None:
        s = _splitter(chunk_size=50)
        raw = [RawChunk(text="sentence one. " * 10)]
        chunks = s.split(raw)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_metadata_propagated(self) -> None:
        s = _splitter()
        raw = [RawChunk(
            text="Test text for metadata propagation.",
            page_number=3,
            section="Policies",
            metadata={"source_format": "pdf", "lang": "en"},
        )]
        chunks = s.split(raw)
        assert len(chunks) == 1
        assert chunks[0].page_number == 3
        assert chunks[0].section == "Policies"
        assert chunks[0].metadata["source_format"] == "pdf"
        assert chunks[0].metadata["lang"] == "en"

    def test_blank_chunks_discarded(self) -> None:
        s = _splitter()
        raw = [RawChunk(text="   \n\n   \n\n   ")]
        chunks = s.split(raw)
        assert len(chunks) == 0

    def test_multiple_raw_chunks_indexed_sequentially(self) -> None:
        s = _splitter(chunk_size=50)
        raw = [
            RawChunk(text="First section content here."),
            RawChunk(text="Second section content here."),
        ]
        chunks = s.split(raw)
        # chunk indices start from 0 and increase
        assert chunks[0].chunk_index == 0
        assert chunks[-1].chunk_index == len(chunks) - 1

    def test_splits_standard_english_sentence_boundaries(self) -> None:
        s = _splitter(chunk_size=60)
        text = "Check-in is at 2 PM. Check-out is at 11 AM. Late checkout costs NPR 500."
        raw = [RawChunk(text=text)]
        chunks = s.split(raw)
        assert len(chunks) >= 2

    def test_nepali_and_english_mixed_text(self) -> None:
        s = _splitter(chunk_size=80)
        text = "Check-in दिउँसो २ बजे हुन्छ। Check-out बिहान ११ बजे। Late checkout रू ५०० लाग्छ।"
        raw = [RawChunk(text=text)]
        chunks = s.split(raw)
        # Should split, not crash
        assert len(chunks) >= 1
        for c in chunks:
            assert isinstance(c.text, str)
            assert len(c.text) > 0
