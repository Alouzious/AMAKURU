"""Run evaluation against golden questions."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from amakuru.core.settings import Settings
from amakuru.modules.evaluation.metrics import decision_matches, rank_of, summarise
from amakuru.modules.evaluation.models import EvalResult, EvalRun, GoldenQuestion
from amakuru.modules.retrieval.providers.embeddings import build_embedding_provider
from amakuru.modules.retrieval.providers.reranker import build_reranker
from amakuru.modules.retrieval.service import retrieve
from amakuru.modules.retrieval.vector_store import PgVectorStore


async def run_eval(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    settings: Settings,
    trigger: str = "manual",
) -> dict[str, Any]:
    goldens = (
        (
            await session.execute(
                select(GoldenQuestion).where(
                    GoldenQuestion.tenant_id == tenant_id,
                    GoldenQuestion.is_active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )

    embedder = build_embedding_provider(settings)
    reranker = build_reranker(settings)
    store = PgVectorStore()

    ranks: list[int | None] = []
    decisions: list[str] = []
    expected_decisions: list[str] = []
    has_expected: list[bool] = []
    run = EvalRun(
        id=uuid4(),
        tenant_id=tenant_id,
        trigger=trigger,
        thresholds={
            "score_verbatim_threshold": settings.score_verbatim_threshold,
            "score_answer_threshold": settings.score_answer_threshold,
            "score_clarify_threshold": settings.score_clarify_threshold,
        },
    )
    session.add(run)
    await session.flush()

    for g in goldens:
        result = await retrieve(
            session,
            tenant_id=tenant_id,
            question=g.question,
            language=g.language,
            settings=settings,
            embedder=embedder,
            reranker=reranker,
            store=store,
        )
        cand_ids = [UUID(c["entry_id"]) for c in result["candidates"]]
        r = rank_of(g.expected_entry_id, cand_ids)
        ranks.append(r)
        decisions.append(result["decision"])
        expected = g.expected_decision
        expected_decisions.append(expected)
        has_expected.append(g.expected_entry_id is not None)
        decision_match = decision_matches(result["decision"], expected)
        correct = decision_match and (r == 1 if g.expected_entry_id else True)
        session.add(
            EvalResult(
                id=uuid4(),
                tenant_id=tenant_id,
                run_id=run.id,
                golden_id=g.id,
                decision=result["decision"],
                top_entry_id=UUID(result["entry_id"]) if result["entry_id"] else None,
                top_score=float(result["score"]),
                rank_of_expected=r,
                correct=correct,
                detail={"trace_id": result["trace_id"], "reason": result["reason"]},
            )
        )

    metrics = summarise(
        ranks=ranks,
        decisions=decisions,
        expected_decisions=expected_decisions,
        has_expected_entry=has_expected,
    )
    passed = (
        metrics["n"] > 0
        and metrics["n_ranked"] > 0
        and metrics["recall_at_1"] >= 0.5
        and metrics["mrr"] >= 0.5
        and metrics["top_one_accuracy"] >= 0.5
    )
    run.metrics = metrics
    run.passed = passed
    await session.flush()
    return {
        "run_id": str(run.id),
        "passed": passed,
        "metrics": metrics,
        "thresholds": run.thresholds,
    }


def format_report(payload: dict[str, Any]) -> str:
    m = payload["metrics"]
    lines = [
        "Amakuru evaluation report",
        "-------------------------",
        f"run_id:  {payload['run_id']}",
        f"passed:  {payload['passed']}",
        f"n:       {m.get('n', 0)}",
        f"n_ranked:{m.get('n_ranked', 0)}",
        f"recall@1:{m.get('recall_at_1', 0):.3f}",
        f"recall@5:{m.get('recall_at_5', 0):.3f}",
        f"mrr:     {m.get('mrr', 0):.3f}",
        f"top-one: {m.get('top_one_accuracy', 0):.3f}",
        f"decision:{m.get('decision_accuracy', 0):.3f}",
    ]
    return "\n".join(lines)
