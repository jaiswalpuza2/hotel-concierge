"""Unit tests for the embedding provider interface and implementations.

We mock the heavy model loading so tests run fast without downloading models.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.rag.embedder import (
    EmbeddingProvider,
    OpenAIEmbedder,
    SentenceTransformerEmbedder,
    get_embedder,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DIM = 768
_FAKE_VECTOR = [0.01] * _DIM


def _make_st_embedder() -> SentenceTransformerEmbedder:
    return SentenceTransformerEmbedder(
        model_name="paraphrase-multilingual-mpnet-base-v2",
        dimensions=_DIM,
    )


# ---------------------------------------------------------------------------
# Abstract interface contract
# ---------------------------------------------------------------------------


class TestEmbeddingProviderInterface:
    def test_sentence_transformer_is_provider(self) -> None:
        assert isinstance(_make_st_embedder(), EmbeddingProvider)

    def test_openai_is_provider(self) -> None:
        emb = OpenAIEmbedder("text-embedding-3-small", "fake-key", 1536)
        assert isinstance(emb, EmbeddingProvider)

    def test_dimensions_property(self) -> None:
        assert _make_st_embedder().dimensions == _DIM
        assert OpenAIEmbedder("model", "key", 512).dimensions == 512


# ---------------------------------------------------------------------------
# SentenceTransformerEmbedder (mocked model)
# ---------------------------------------------------------------------------


class TestSentenceTransformerEmbedder:
    @pytest.fixture
    def mock_st_model(self):
        """Patch SentenceTransformer so it doesn't download a real model."""
        import numpy as np

        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([_FAKE_VECTOR, _FAKE_VECTOR])
        with patch("app.rag.embedder.SentenceTransformerEmbedder._load_model"):
            emb = _make_st_embedder()
            emb._model = mock_model
            yield emb

    async def test_embed_returns_correct_count(self, mock_st_model: SentenceTransformerEmbedder) -> None:
        texts = ["hello", "world"]
        result = await mock_st_model.embed(texts)
        assert len(result) == 2

    async def test_embed_returns_correct_dimensions(self, mock_st_model: SentenceTransformerEmbedder) -> None:
        result = await mock_st_model.embed(["test"])
        assert len(result[0]) == _DIM

    async def test_embed_empty_list_returns_empty(self, mock_st_model: SentenceTransformerEmbedder) -> None:
        result = await mock_st_model.embed([])
        assert result == []

    async def test_embed_query_returns_single_vector(self, mock_st_model: SentenceTransformerEmbedder) -> None:
        import numpy as np
        mock_st_model._model.encode.return_value = np.array([_FAKE_VECTOR])
        result = await mock_st_model.embed_query("room price kati?")
        assert len(result) == _DIM

    async def test_embed_nepali_text(self, mock_st_model: SentenceTransformerEmbedder) -> None:
        import numpy as np
        mock_st_model._model.encode.return_value = np.array([_FAKE_VECTOR])
        result = await mock_st_model.embed(["कोठाको मूल्य कति हो?"])
        assert len(result) == 1
        assert len(result[0]) == _DIM


# ---------------------------------------------------------------------------
# OpenAIEmbedder (mocked HTTP)
# ---------------------------------------------------------------------------


class TestOpenAIEmbedder:
    def _make_embedder(self, dim: int = 1536) -> OpenAIEmbedder:
        return OpenAIEmbedder("text-embedding-3-small", "sk-fake", dim)

    @pytest.fixture
    def mock_response(self):
        """Fake a successful OpenAI embeddings API response."""
        fake_vec = [0.01] * 1536
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {"index": 0, "embedding": fake_vec},
                {"index": 1, "embedding": fake_vec},
            ]
        }
        return mock_resp

    async def test_embed_calls_api_and_returns_vectors(self, mock_response) -> None:
        emb = self._make_embedder(1536)
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            result = await emb.embed(["text one", "text two"])
        assert len(result) == 2
        assert len(result[0]) == 1536

    async def test_embed_empty_list_returns_empty(self) -> None:
        emb = self._make_embedder()
        result = await emb.embed([])
        assert result == []

    async def test_embed_api_error_raises_provider_error(self) -> None:
        from app.exceptions import ProviderError

        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = "Rate limit exceeded"

        emb = self._make_embedder()
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp), \
             pytest.raises(ProviderError) as exc:
            await emb.embed(["text"])
        assert exc.value.code == "openai_embed_error"

    async def test_results_ordered_by_index(self, mock_response) -> None:
        """Results must maintain input order even if API returns out of order."""
        vec_a = [1.0] * 1536
        vec_b = [2.0] * 1536
        mock_response.json.return_value = {
            "data": [
                {"index": 1, "embedding": vec_b},  # deliberately out of order
                {"index": 0, "embedding": vec_a},
            ]
        }
        emb = self._make_embedder(1536)
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            result = await emb.embed(["first", "second"])
        # index 0 must come first
        assert result[0][0] == 1.0  # vec_a
        assert result[1][0] == 2.0  # vec_b


# ---------------------------------------------------------------------------
# get_embedder factory
# ---------------------------------------------------------------------------


class TestGetEmbedder:
    def test_returns_sentence_transformer_by_default(self) -> None:
        import os
        os.environ["EMBEDDING_PROVIDER"] = "sentence_transformer"
        from app.config import get_settings
        get_settings.cache_clear()
        get_embedder.cache_clear()
        embedder = get_embedder()
        assert isinstance(embedder, SentenceTransformerEmbedder)
        get_embedder.cache_clear()

    def test_returns_openai_when_configured(self) -> None:
        import os
        os.environ["EMBEDDING_PROVIDER"] = "openai"
        os.environ["LLM_API_KEY"] = "sk-test"
        from app.config import get_settings
        get_settings.cache_clear()
        get_embedder.cache_clear()
        embedder = get_embedder()
        assert isinstance(embedder, OpenAIEmbedder)
        get_embedder.cache_clear()
        os.environ["EMBEDDING_PROVIDER"] = "sentence_transformer"
        get_settings.cache_clear()
