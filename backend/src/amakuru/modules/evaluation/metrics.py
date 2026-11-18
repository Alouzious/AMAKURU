"""Retrieval evaluation metrics."""

from __future__ import annotations

from typing import Any
from uuid import UUID


def recall_at_k(ranks: list[int | None], *, k: int) -> float:
    if not ranks:
        return 0.0
    hits = sum(1 for r in ranks if r is not None and r <= k)
    return hits / len(ranks)


def mean_reciprocal_rank(ranks: list[int | None]) -> float:
    if not ranks:
        return 0.0
    total = 0.0
    for r in ranks:
        if r is not None and r > 0:
            total += 1.0 / r
    return total / len(ranks)


def top_one_accuracy(ranks: list[int | None]) -> float:
    if not ranks:
        return 0.0
    return sum(1 for r in ranks if r == 1) / len(ranks)


def decision_matches(actual: str, expected: str) -> bool:
    if expected in {"answer", "verbatim", "compose"}:
        return actual in {"verbatim", "compose"}
    return actual == expected


def summarise(
    *,
    ranks: list[int | None],
    decisions: list[str],
    expected_decisions: list[str],
    has_expected_entry: list[bool],
) -> dict[str, Any]:
    ranked = [r for r, keep in zip(ranks, has_expected_entry, strict=True) if keep]
    decision_ok = [
        decision_matches(d, e) for d, e in zip(decisions, expected_decisions, strict=True)
    ]
    return {
        "n": len(ranks),
        "n_ranked": len(ranked),
        "recall_at_1": recall_at_k(ranked, k=1),
        "recall_at_5": recall_at_k(ranked, k=5),
        "mrr": mean_reciprocal_rank(ranked),
        "top_one_accuracy": top_one_accuracy(ranked),
        "decision_accuracy": (sum(decision_ok) / len(decision_ok)) if decision_ok else 0.0,
    }


def rank_of(expected: UUID | None, candidate_entry_ids: list[UUID]) -> int | None:
    if expected is None:
        return None
    for i, eid in enumerate(candidate_entry_ids, start=1):
        if eid == expected:
            return i
    return None
