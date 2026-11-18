"""Unit tests for retrieval metrics and decision policy."""

from __future__ import annotations

import uuid

from amakuru.core.settings import get_settings
from amakuru.modules.evaluation.metrics import (
    mean_reciprocal_rank,
    recall_at_k,
    summarise,
    top_one_accuracy,
)
from amakuru.modules.retrieval.decision import Decision, decide
from amakuru.modules.retrieval.hybrid import Candidate, reciprocal_rank_fusion


def test_metrics_basic() -> None:
    ranks = [1, 2, None, 1]
    assert recall_at_k(ranks, k=1) == 0.5
    assert recall_at_k(ranks, k=5) == 0.75
    assert top_one_accuracy(ranks) == 0.5
    assert mean_reciprocal_rank(ranks) == (1 + 0.5 + 0 + 1) / 4
    summary = summarise(
        ranks=ranks,
        decisions=["verbatim", "handoff", "greeting", "compose"],
        expected_decisions=["verbatim", "handoff", "greeting", "answer"],
        has_expected_entry=[True, False, False, True],
    )
    assert summary["n_ranked"] == 2
    assert summary["recall_at_1"] == 1.0


def test_rrf() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    scores = reciprocal_rank_fusion([[a, b], [b, c]])
    assert scores[b] > scores[a]
    assert scores[b] > scores[c]


def test_decide_verbatim_and_handoff() -> None:
    settings = get_settings()
    cand = Candidate(
        entry_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
        office_id=uuid.uuid4(),
        answer_text="demo",
        question_text="q",
        verbatim_only=True,
        escalate_to_human=False,
        score=0.9,
    )
    assert decide("what fees", [cand], settings).decision == Decision.VERBATIM
    assert decide("hello", [], settings).decision == Decision.GREETING
    weak = Candidate(
        entry_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
        office_id=uuid.uuid4(),
        answer_text="x",
        question_text=None,
        verbatim_only=False,
        escalate_to_human=False,
        score=0.1,
    )
    assert decide("obscure question", [weak], settings).decision == Decision.HANDOFF
