"""Embedding provider interface and implementations.

The ``EmbeddingProvider`` abstract class defines the contract.
Two concrete implementations are provided:

- ``SentenceTransformerEmbedder``: uses ``paraphrase-multilingual-mpnet-base-v2``
  (768 dimensions, runs locally with no API key, supports Nepali).
- ``OpenAIEmbedder``: uses the OpenAI embeddings API (requires API key).

The active provider is selected by ``EMBEDDING_PROVIDER`` env var and returned
by ``get_embedder()`` which is cached for the process lifetime.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Maximum number of texts to embed in one batch call.
# sentence-transformers handles batching internally; OpenAI has a 2048-input limit.
_DEFAULT_BATCH_SIZE = 64


class EmbeddingProvider(ABC):
    """Abstract base class for all embedding providers.

    All implementations must be thread-safe and reusable across requests.
    """

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Return the number of dimensions in each embedding vector."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts.

        Args:
            texts: List of strings to embed. Each string should be a single
                document chunk (not a query). For query embedding use
                ``embed_query`` which some providers optimise differently.

        Returns:
            List of float vectors, one per input text, in the same order.
            Each vector has ``self.dimensions`` elements.
        """

    async def embed_query(self, query: str) -> list[float]:
        """Embed a single query string.

        By default calls ``embed([query])[0]``. Override if the provider
        uses a different encoding for queries vs documents (e.g. asymmetric).
        """
        results = await self.embed([query])
        return results[0]


class SentenceTransformerEmbedder(EmbeddingProvider):
    """Local multilingual embedding using sentence-transformers.

    Default model: ``paraphrase-multilingual-mpnet-base-v2``
    - 768 dimensions
    - Supports 50+ languages including Nepali
    - Runs on CPU (no GPU required for the demo scale)
    - Downloaded once to ~/.cache/huggingface on first use (~420 MB)

    The model is loaded lazily on first embed call to avoid slowing
    application startup.
    """

    def __init__(self, model_name: str, dimensions: int) -> None:
        self._model_name = model_name
        self._dimensions = dimensions
        self._model: Any = None  # loaded lazily

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _load_model(self) -> None:
        """Load the sentence-transformers model (called once, thread-safe via GIL)."""
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import]
            logger.info(
                "embedder.loading_model",
                model=self._model_name,
                provider="sentence_transformer",
            )
            self._model = SentenceTransformer(self._model_name)
            logger.info("embedder.model_loaded", model=self._model_name)
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is not installed. "
                "Run: pip install sentence-transformers"
            ) from exc

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts using the local sentence-transformers model.

        Runs in a thread pool to avoid blocking the event loop
        (model inference is CPU-bound).
        """
        import asyncio

        if not texts:
            return []

        self._load_model()

        def _encode() -> list[list[float]]:
            assert self._model is not None
            vectors = self._model.encode(
                texts,
                batch_size=_DEFAULT_BATCH_SIZE,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            return [v.tolist() for v in vectors]

        result = await asyncio.to_thread(_encode)
        logger.debug(
            "embedder.embedded",
            provider="sentence_transformer",
            count=len(texts),
            dimensions=self._dimensions,
        )
        return result


class OpenAIEmbedder(EmbeddingProvider):
    """Embedding via the OpenAI embeddings API.

    Model: configurable via ``OPENAI_EMBEDDING_MODEL`` env var.
    Default: ``text-embedding-3-small`` (1536 dimensions, very fast).

    Note: OpenAI embedding models are English-centric; multilingual
    quality for Nepali may be lower than sentence-transformers.
    """

    def __init__(self, model_name: str, api_key: str, dimensions: int) -> None:
        self._model_name = model_name
        self._api_key = api_key
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Call the OpenAI embeddings API for the given texts."""
        import httpx

        if not texts:
            return []

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model_name,
            "input": texts,
            "encoding_format": "float",
            # text-embedding-3-* can return fewer dimensions; this keeps vectors compatible
            # with the vector(768) column.
            "dimensions": self._dimensions,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers=headers,
                json=payload,
            )

        if response.status_code != 200:
            from app.exceptions import ProviderError
            raise ProviderError(
                "OpenAI embeddings API error",
                code="openai_embed_error",
                details={"status": response.status_code, "body": response.text[:200]},
            )

        data = response.json()
        # API returns results sorted by index — preserve order
        vectors = sorted(data["data"], key=lambda x: x["index"])
        result = [item["embedding"] for item in vectors]

        logger.debug(
            "embedder.embedded",
            provider="openai",
            model=self._model_name,
            count=len(texts),
        )
        return result


class HashingEmbedder(EmbeddingProvider):
    """Dependency-free, deterministic embedder for development, demos and CI.

    Hashes word unigrams/bigrams and character 3-grams into a fixed-size vector
    (the "hashing trick") and L2-normalises it. It captures lexical overlap only,
    NOT meaning, so production should use ``sentence_transformer`` or ``openai``.
    Cosine scores are much lower than neural models, so lower
    ``RETRIEVAL_CONFIDENCE_THRESHOLD`` (e.g. 0.15) when using it.
    """

    def __init__(self, dimensions: int) -> None:
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _vectorise(self, text: str) -> list[float]:
        import hashlib
        import math
        import re

        vec = [0.0] * self._dimensions
        words = re.findall(r"[\w\u0900-\u097F]+", text.lower())
        features: list[tuple[str, float]] = [(w, 1.0) for w in words]
        features += [(f"{a}_{b}", 0.7) for a, b in zip(words, words[1:], strict=False)]
        for w in words:
            padded = f"#{w}#"
            features += [(padded[i : i + 3], 0.3) for i in range(max(1, len(padded) - 2))]
        for token, weight in features:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "big")
            sign = 1.0 if (value >> 40) & 1 else -1.0
            vec[value % self._dimensions] += sign * weight
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vectorise(t) for t in texts]


@lru_cache(maxsize=1)
def get_embedder() -> EmbeddingProvider:
    """Return the configured EmbeddingProvider instance (cached for process lifetime).

    Provider selected by ``EMBEDDING_PROVIDER`` env var:
    - ``sentence_transformer`` (default): uses local model
    - ``openai``: uses OpenAI API

    Returns:
        An ``EmbeddingProvider`` ready to call ``embed()``.
    """
    from app.config import get_settings

    settings = get_settings()

    if settings.embedding_provider == "hashing":
        logger.warning("embedder.selected", provider="hashing", note="lexical only - development use")
        return HashingEmbedder(dimensions=settings.embedding_dimensions)

    if settings.embedding_provider == "openai":
        logger.info(
            "embedder.selected",
            provider="openai",
            model=settings.openai_embedding_model,
        )
        return OpenAIEmbedder(
            model_name=settings.openai_embedding_model,
            api_key=(settings.embedding_api_key.get_secret_value() or settings.llm_api_key.get_secret_value()),
            dimensions=settings.embedding_dimensions,
        )

    # Default: sentence_transformer
    logger.info(
        "embedder.selected",
        provider="sentence_transformer",
        model=settings.embedding_model,
    )
    return SentenceTransformerEmbedder(
        model_name=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )
