"""The offline hashing embedder: deterministic, normalised, and lexically meaningful."""
from __future__ import annotations

import asyncio
import math

from app.rag.embedder import HashingEmbedder


def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_vectors_are_unit_length_and_deterministic():
    emb = HashingEmbedder(768)
    first, second = asyncio.run(emb.embed(["Check-out is at 11:00 AM", "Check-out is at 11:00 AM"]))
    assert len(first) == 768 and first == second
    assert math.isclose(math.sqrt(sum(x * x for x in first)), 1.0, rel_tol=1e-6)


def test_relevant_text_scores_higher_than_unrelated():
    emb = HashingEmbedder(768)
    docs = asyncio.run(emb.embed(["Check-out time is 11:00 AM", "The restaurant serves dal bhat and momo"]))
    query = asyncio.run(emb.embed_query("what time is check-out"))
    assert _cos(query, docs[0]) > _cos(query, docs[1])
