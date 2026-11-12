"""Reranker providers."""

from __future__ import annotations

from typing import Protocol

from amakuru.core.settings import Settings


class RerankerProvider(Protocol):
    async def rerank(
        self, query: str, documents: list[str], *, top_k: int
    ) -> list[tuple[int, float]]:
        """Return (original_index, score) sorted best-first."""
        ...


class IdentityReranker:
    """Keeps candidate order; assigns decreasing scores from existing ranks."""

    async def rerank(
        self, query: str, documents: list[str], *, top_k: int
    ) -> list[tuple[int, float]]:
        ranked = [(i, 1.0 - (i * 0.01)) for i in range(len(documents))]
        return ranked[:top_k]


class LexicalBoostReranker:
    """Lightweight reranker: boosts overlap of query tokens with document text."""

    async def rerank(
        self, query: str, documents: list[str], *, top_k: int
    ) -> list[tuple[int, float]]:
        q_tokens = {t for t in query.lower().split() if t}
        scored: list[tuple[int, float]] = []
        for i, doc in enumerate(documents):
            d_tokens = doc.lower().split()
            if not d_tokens:
                scored.append((i, 0.0))
                continue
            overlap = sum(1 for t in d_tokens if t in q_tokens)
            score = overlap / max(len(q_tokens), 1)
            # Slight preference for earlier hybrid ranks
            score = score * 0.85 + (1.0 - i * 0.01) * 0.15
            scored.append((i, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]


def build_reranker(settings: Settings) -> RerankerProvider:
    if not settings.reranker_enabled:
        return IdentityReranker()
    # Full cross-encoder (bge-reranker-v2-m3) is optional; lexical boost is the
    # offline-safe default that still improves hybrid ranking for eval.
    return LexicalBoostReranker()
