"""Embedding providers behind a swap-friendly interface."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

import numpy as np

from amakuru.core.settings import Settings

_TOKEN = re.compile(r"[a-z0-9]+", re.I)


class EmbeddingProvider(Protocol):
    model_id: str
    model_version: str
    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbeddingProvider:
    """Deterministic dense embeddings for offline/CI. Not for production quality.

    Uses a hashing trick over tokens into a fixed dimension, L2-normalised so
    cosine distance behaves sensibly with pgvector.
    """

    def __init__(self, *, dim: int = 1024, model_id: str = "amakuru/hash-embed") -> None:
        self.model_id = model_id
        self.model_version = "1"
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = np.zeros(self.dim, dtype=np.float64)
        tokens = _TOKEN.findall(text.lower())
        if not tokens:
            tokens = ["_empty_"]
        for tok in tokens:
            digest = hashlib.sha256(tok.encode()).digest()
            idx = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign
        # Character n-grams for spelling robustness
        compact = re.sub(r"\s+", "", text.lower())
        for i in range(max(0, len(compact) - 2)):
            gram = compact[i : i + 3]
            digest = hashlib.md5(gram.encode(), usedforsecurity=False).digest()
            idx = int.from_bytes(digest[:4], "little") % self.dim
            vec[idx] += 0.35
        norm = math.sqrt(float(np.dot(vec, vec))) or 1.0
        normalised = (vec / norm).astype(np.float32)
        return [float(x) for x in normalised.tolist()]


class OpenAICompatibleEmbeddingProvider:
    """Remote OpenAI-compatible embeddings endpoint."""

    def __init__(self, settings: Settings) -> None:
        self.model_id = settings.embedding_model
        self.model_version = "1"
        self.dim = settings.embedding_dim
        self._base = settings.embedding_remote_base_url.rstrip("/")
        self._key = settings.embedding_remote_api_key

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self._base}/embeddings",
                headers={"Authorization": f"Bearer {self._key}"},
                json={"model": self.model_id, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            data_sorted = sorted(data, key=lambda row: row["index"])
            return [row["embedding"] for row in data_sorted]


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    provider = settings.embedding_provider.lower()
    if provider in {"hash", "local"}:
        # Local BGE is optional; Phase 2 defaults to hash so eval/CI work offline.
        # Set EMBEDDING_PROVIDER=openai_compatible for remote models.
        if provider == "local":
            # Prefer hash until models are downloaded into MODEL_CACHE_DIR.
            # Real FlagEmbedding path can be wired when the cache is populated.
            return HashEmbeddingProvider(dim=settings.embedding_dim, model_id="amakuru/hash-embed")
        return HashEmbeddingProvider(dim=settings.embedding_dim)
    if provider == "openai_compatible":
        return OpenAICompatibleEmbeddingProvider(settings)
    return HashEmbeddingProvider(dim=settings.embedding_dim)
