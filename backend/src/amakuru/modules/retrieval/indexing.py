"""Index published knowledge into embeddings."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from amakuru.core.settings import Settings
from amakuru.modules.knowledge.models import STATUS_PUBLISHED, AnswerVersion, QuestionVariant
from amakuru.modules.retrieval.models import SOURCE_ANSWER_VERSION, SOURCE_QUESTION_VARIANT
from amakuru.modules.retrieval.providers.embeddings import EmbeddingProvider
from amakuru.modules.retrieval.vector_store import PgVectorStore


async def index_tenant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    embedder: EmbeddingProvider,
    store: PgVectorStore,
    settings: Settings,
) -> dict[str, Any]:
    versions = (
        (
            await session.execute(
                select(AnswerVersion).where(
                    AnswerVersion.tenant_id == tenant_id,
                    AnswerVersion.status == STATUS_PUBLISHED,
                )
            )
        )
        .scalars()
        .all()
    )
    variants = (
        (
            await session.execute(
                select(QuestionVariant).where(QuestionVariant.tenant_id == tenant_id)
            )
        )
        .scalars()
        .all()
    )

    # Only variants linked to published entries
    published_entries = {v.entry_id for v in versions}
    variants = [v for v in variants if v.entry_id in published_entries]

    texts: list[str] = []
    meta: list[tuple[str, uuid.UUID]] = []
    for v in versions:
        texts.append(v.answer_text)
        meta.append((SOURCE_ANSWER_VERSION, v.id))
    for q in variants:
        texts.append(q.raw_text)
        meta.append((SOURCE_QUESTION_VARIANT, q.id))

    if not texts:
        return {"indexed": 0, "versions": 0, "variants": 0}

    vectors = await embedder.embed(texts)
    for (source_type, source_id), dense in zip(meta, vectors, strict=True):
        await store.upsert(
            session,
            tenant_id=tenant_id,
            source_type=source_type,
            source_id=source_id,
            model_id=embedder.model_id,
            model_version=embedder.model_version,
            dense=dense,
        )
    return {
        "indexed": len(texts),
        "versions": len(versions),
        "variants": len(variants),
        "model_id": embedder.model_id,
    }
