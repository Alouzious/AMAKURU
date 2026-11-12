"""VectorStore interface and pgvector implementation."""

from __future__ import annotations

import json
import uuid
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _vec_literal(dense: list[float]) -> str:
    return "[" + ",".join(f"{float(x):.8f}" for x in dense) + "]"


class VectorStore(Protocol):
    async def upsert(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        source_type: str,
        source_id: uuid.UUID,
        model_id: str,
        model_version: str,
        dense: list[float],
        sparse_weights: dict[str, Any] | None = None,
    ) -> uuid.UUID: ...

    async def search(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        dense: list[float],
        model_id: str,
        limit: int,
        source_type: str | None = None,
    ) -> list[tuple[uuid.UUID, str, uuid.UUID, float]]:
        """Return (embedding_id, source_type, source_id, score)."""
        ...


class PgVectorStore:
    async def upsert(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        source_type: str,
        source_id: uuid.UUID,
        model_id: str,
        model_version: str,
        dense: list[float],
        sparse_weights: dict[str, Any] | None = None,
    ) -> uuid.UUID:
        emb_id = uuid.uuid4()
        await session.execute(
            text(
                """
                INSERT INTO embeddings
                  (id, tenant_id, source_type, source_id, model_id, model_version,
                   dense, sparse_weights)
                VALUES
                  (CAST(:id AS uuid), CAST(:tenant_id AS uuid), :source_type,
                   CAST(:source_id AS uuid), :model_id, :model_version,
                   CAST(:dense AS vector), CAST(:sparse AS jsonb))
                ON CONFLICT (tenant_id, source_type, source_id, model_id, model_version)
                DO UPDATE SET
                  dense = EXCLUDED.dense,
                  sparse_weights = EXCLUDED.sparse_weights
                RETURNING id
                """
            ),
            {
                "id": str(emb_id),
                "tenant_id": str(tenant_id),
                "source_type": source_type,
                "source_id": str(source_id),
                "model_id": model_id,
                "model_version": model_version,
                "dense": _vec_literal(dense),
                "sparse": json.dumps(sparse_weights or {}),
            },
        )
        # Fetch canonical id after upsert
        result = await session.execute(
            text(
                """
                SELECT id FROM embeddings
                WHERE tenant_id = CAST(:tenant_id AS uuid)
                  AND source_type = :source_type
                  AND source_id = CAST(:source_id AS uuid)
                  AND model_id = :model_id
                  AND model_version = :model_version
                """
            ),
            {
                "tenant_id": str(tenant_id),
                "source_type": source_type,
                "source_id": str(source_id),
                "model_id": model_id,
                "model_version": model_version,
            },
        )
        row = result.one()
        return uuid.UUID(str(row[0]))

    async def search(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        dense: list[float],
        model_id: str,
        limit: int,
        source_type: str | None = None,
    ) -> list[tuple[uuid.UUID, str, uuid.UUID, float]]:
        params: dict[str, Any] = {
            "tenant_id": str(tenant_id),
            "model_id": model_id,
            "limit": limit,
            "q": _vec_literal(dense),
        }
        source_clause = ""
        if source_type:
            source_clause = "AND source_type = :source_type"
            params["source_type"] = source_type
        sql = text(
            f"""
            SELECT id, source_type, source_id,
                   1 - (dense <=> CAST(:q AS vector)) AS score
            FROM embeddings
            WHERE tenant_id = CAST(:tenant_id AS uuid)
              AND model_id = :model_id
              {source_clause}
            ORDER BY dense <=> CAST(:q AS vector)
            LIMIT :limit
            """
        )
        result = await session.execute(sql, params)
        rows = []
        for emb_id, stype, sid, score in result.fetchall():
            rows.append((uuid.UUID(str(emb_id)), stype, uuid.UUID(str(sid)), float(score or 0.0)))
        return rows

    async def delete_for_source(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        source_type: str,
        source_id: uuid.UUID,
    ) -> None:
        await session.execute(
            text(
                """
                DELETE FROM embeddings
                WHERE tenant_id = CAST(:tenant_id AS uuid)
                  AND source_type = :source_type
                  AND source_id = CAST(:source_id AS uuid)
                """
            ),
            {
                "tenant_id": str(tenant_id),
                "source_type": source_type,
                "source_id": str(source_id),
            },
        )
