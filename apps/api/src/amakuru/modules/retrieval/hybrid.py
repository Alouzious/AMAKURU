"""Hybrid dense + keyword retrieval with reciprocal rank fusion."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from amakuru.modules.knowledge.models import (
    STATUS_PUBLISHED,
    AnswerEntry,
    AnswerVersion,
    QuestionVariant,
)
from amakuru.modules.retrieval.models import SOURCE_ANSWER_VERSION, SOURCE_QUESTION_VARIANT
from amakuru.modules.retrieval.vector_store import PgVectorStore


@dataclass
class Candidate:
    entry_id: uuid.UUID
    version_id: uuid.UUID
    office_id: uuid.UUID
    answer_text: str
    question_text: str | None
    verbatim_only: bool
    escalate_to_human: bool
    score: float
    dense_rank: int | None = None
    keyword_rank: int | None = None
    rerank_score: float | None = None


def reciprocal_rank_fusion(
    ranked_lists: list[list[uuid.UUID]], *, k: int = 60
) -> dict[uuid.UUID, float]:
    scores: dict[uuid.UUID, float] = {}
    for ranked in ranked_lists:
        for rank, item_id in enumerate(ranked, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return scores


async def keyword_search(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    query: str,
    limit: int,
) -> list[tuple[uuid.UUID, uuid.UUID, float]]:
    """Return (entry_id, version_id, rank_score) via exact/ILIKE + FTS."""
    sql = text(
        """
        WITH published AS (
          SELECT v.id AS version_id, v.entry_id, v.search_tsv, v.answer_text
          FROM answer_versions v
          WHERE v.tenant_id = CAST(:tenant_id AS uuid)
            AND v.status = 'published'
            AND (v.valid_until IS NULL OR v.valid_until >= CURRENT_DATE)
        ),
        q AS (SELECT plainto_tsquery('english', :query) AS tsq),
        scored AS (
          SELECT qv.entry_id, p.version_id,
                 CASE
                   WHEN lower(qv.raw_text) = lower(:query) THEN 100.0
                   WHEN lower(qv.raw_text) LIKE lower('%' || :query || '%') THEN 50.0
                   WHEN lower(:query) LIKE lower('%' || qv.raw_text || '%') THEN 40.0
                   WHEN qv.search_tsv @@ q.tsq THEN ts_rank_cd(qv.search_tsv, q.tsq) * 10.0
                   ELSE 0.0
                 END AS score
          FROM question_variants qv
          JOIN published p ON p.entry_id = qv.entry_id
          CROSS JOIN q
          WHERE qv.tenant_id = CAST(:tenant_id AS uuid)
          UNION ALL
          SELECT p.entry_id, p.version_id,
                 CASE
                   WHEN p.search_tsv @@ q.tsq THEN ts_rank_cd(p.search_tsv, q.tsq) * 5.0
                   ELSE 0.0
                 END AS score
          FROM published p
          CROSS JOIN q
        )
        SELECT entry_id, version_id, score
        FROM scored
        WHERE score > 0
        ORDER BY score DESC
        LIMIT :limit
        """
    )
    result = await session.execute(
        sql, {"tenant_id": str(tenant_id), "query": query, "limit": limit}
    )
    out: list[tuple[uuid.UUID, uuid.UUID, float]] = []
    seen: set[uuid.UUID] = set()
    for entry_id, version_id, score in result.fetchall():
        eid = uuid.UUID(str(entry_id))
        if eid in seen:
            continue
        seen.add(eid)
        out.append((eid, uuid.UUID(str(version_id)), float(score or 0.0)))
    return out


async def dense_search_entries(
    session: AsyncSession,
    store: PgVectorStore,
    *,
    tenant_id: uuid.UUID,
    dense: list[float],
    model_id: str,
    limit: int,
) -> list[tuple[uuid.UUID, uuid.UUID, float]]:
    """Map embedding hits (variants/versions) to published entry/version pairs."""
    hits = await store.search(
        session,
        tenant_id=tenant_id,
        dense=dense,
        model_id=model_id,
        limit=limit * 3,
    )
    # Resolve to published versions
    published = await session.execute(
        select(AnswerVersion).where(
            AnswerVersion.tenant_id == tenant_id,
            AnswerVersion.status == STATUS_PUBLISHED,
        )
    )
    pub_by_entry = {v.entry_id: v for v in published.scalars().all()}
    # Filter expired
    from datetime import date

    today = date.today()
    pub_by_entry = {
        eid: v for eid, v in pub_by_entry.items() if v.valid_until is None or v.valid_until >= today
    }

    variant_ids = [sid for _eid, st, sid, _sc in hits if st == SOURCE_QUESTION_VARIANT]
    version_ids = [sid for _eid, st, sid, _sc in hits if st == SOURCE_ANSWER_VERSION]

    variant_map: dict[uuid.UUID, uuid.UUID] = {}
    if variant_ids:
        rows = await session.execute(
            select(QuestionVariant.id, QuestionVariant.entry_id).where(
                QuestionVariant.id.in_(variant_ids)
            )
        )
        variant_map = {vid: eid for vid, eid in rows.all()}

    version_map: dict[uuid.UUID, uuid.UUID] = {}
    if version_ids:
        rows = await session.execute(
            select(AnswerVersion.id, AnswerVersion.entry_id).where(
                AnswerVersion.id.in_(version_ids)
            )
        )
        version_map = {vid: eid for vid, eid in rows.all()}

    out: list[tuple[uuid.UUID, uuid.UUID, float]] = []
    seen: set[uuid.UUID] = set()
    for _emb_id, stype, sid, score in hits:
        entry_id = (
            variant_map.get(sid) if stype == SOURCE_QUESTION_VARIANT else version_map.get(sid)
        )
        if entry_id is None or entry_id in seen:
            continue
        version = pub_by_entry.get(entry_id)
        if version is None:
            continue
        seen.add(entry_id)
        out.append((entry_id, version.id, score))
        if len(out) >= limit:
            break
    return out


async def hybrid_retrieve(
    session: AsyncSession,
    store: PgVectorStore,
    *,
    tenant_id: uuid.UUID,
    query: str,
    dense: list[float],
    model_id: str,
    top_k: int,
) -> list[Candidate]:
    dense_hits = await dense_search_entries(
        session, store, tenant_id=tenant_id, dense=dense, model_id=model_id, limit=top_k
    )
    kw_hits = await keyword_search(session, tenant_id=tenant_id, query=query, limit=top_k)

    dense_ranks = [eid for eid, _vid, _sc in dense_hits]
    kw_ranks = [eid for eid, _vid, _sc in kw_hits]
    fused = reciprocal_rank_fusion([dense_ranks, kw_ranks])

    version_for_entry: dict[uuid.UUID, uuid.UUID] = {}
    dense_score: dict[uuid.UUID, float] = {eid: sc for eid, _vid, sc in dense_hits}
    kw_score: dict[uuid.UUID, float] = {eid: sc for eid, _vid, sc in kw_hits}
    for eid, vid, _sc in kw_hits + dense_hits:
        if eid not in version_for_entry:
            version_for_entry[eid] = vid

    if not fused:
        return []

    entry_ids = list(fused.keys())
    entries = (
        (
            await session.execute(
                select(AnswerEntry).where(
                    AnswerEntry.id.in_(entry_ids),
                    AnswerEntry.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    entry_map = {e.id: e for e in entries}
    versions = (
        (
            await session.execute(
                select(AnswerVersion).where(AnswerVersion.id.in_(list(version_for_entry.values())))
            )
        )
        .scalars()
        .all()
    )
    version_map = {v.id: v for v in versions}

    variants = (
        (
            await session.execute(
                select(QuestionVariant)
                .where(QuestionVariant.entry_id.in_(entry_ids))
                .order_by(QuestionVariant.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    first_q: dict[uuid.UUID, str] = {}
    for v in variants:
        first_q.setdefault(v.entry_id, v.raw_text)

    dense_rank_map = {eid: i + 1 for i, eid in enumerate(dense_ranks)}
    kw_rank_map = {eid: i + 1 for i, eid in enumerate(kw_ranks)}

    candidates: list[Candidate] = []
    for entry_id, rrf in sorted(fused.items(), key=lambda x: x[1], reverse=True):
        entry = entry_map.get(entry_id)
        version_id = version_for_entry.get(entry_id)
        if entry is None or version_id is None:
            continue
        version = version_map.get(version_id)
        if version is None:
            continue
        # Prefer strong lexical/exact hits; otherwise blend dense + RRF.
        lex = kw_score.get(entry_id, 0.0)
        base = dense_score.get(entry_id, 0.0)
        if lex >= 40.0:
            score = min(0.99, 0.85 + (lex / 1000.0))
        else:
            score = 0.55 * base + 0.25 * min(rrf * 10.0, 1.0) + 0.20 * min(lex / 10.0, 1.0)
        candidates.append(
            Candidate(
                entry_id=entry_id,
                version_id=version.id,
                office_id=entry.office_id,
                answer_text=version.answer_text,
                question_text=first_q.get(entry_id),
                verbatim_only=entry.verbatim_only,
                escalate_to_human=entry.escalate_to_human,
                score=score,
                dense_rank=dense_rank_map.get(entry_id),
                keyword_rank=kw_rank_map.get(entry_id),
            )
        )
        if len(candidates) >= top_k:
            break
    return candidates


def candidate_to_dict(c: Candidate) -> dict[str, Any]:
    return {
        "entry_id": str(c.entry_id),
        "version_id": str(c.version_id),
        "office_id": str(c.office_id),
        "score": c.score,
        "rerank_score": c.rerank_score,
        "dense_rank": c.dense_rank,
        "keyword_rank": c.keyword_rank,
        "verbatim_only": c.verbatim_only,
        "escalate_to_human": c.escalate_to_human,
    }
