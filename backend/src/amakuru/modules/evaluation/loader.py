"""Load golden questions from JSONL into the database."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from amakuru.modules.evaluation.models import GoldenQuestion
from amakuru.modules.knowledge.models import AnswerEntry


async def load_golden_jsonl(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    path: Path,
    entry_slug_map: dict[str, UUID] | None = None,
) -> int:
    """Load/replace active goldens for a tenant from JSONL.

    Each line: {"question", "language", "expected_decision", "expected_entry_key", "tags"}
    expected_entry_key matches AnswerEntry.subcategory for demo convenience, or a UUID.
    """
    if not path.exists():
        return 0

    # Deactivate existing
    existing = (
        (
            await session.execute(
                select(GoldenQuestion).where(
                    GoldenQuestion.tenant_id == tenant_id, GoldenQuestion.is_active.is_(True)
                )
            )
        )
        .scalars()
        .all()
    )
    for g in existing:
        g.is_active = False

    entries = (
        (
            await session.execute(
                select(AnswerEntry).where(
                    AnswerEntry.tenant_id == tenant_id, AnswerEntry.deleted_at.is_(None)
                )
            )
        )
        .scalars()
        .all()
    )
    by_sub = {e.subcategory: e.id for e in entries}
    if entry_slug_map:
        by_sub.update({k: v for k, v in entry_slug_map.items()})

    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row: dict[str, Any] = json.loads(line)
        key = row.get("expected_entry_key")
        expected_id: UUID | None = None
        if key:
            if key in by_sub:
                expected_id = by_sub[key]
            else:
                try:
                    expected_id = UUID(str(key))
                except ValueError:
                    expected_id = None
        session.add(
            GoldenQuestion(
                id=uuid4(),
                tenant_id=tenant_id,
                question=str(row["question"]),
                language=str(row.get("language") or "en"),
                expected_entry_id=expected_id,
                expected_decision=str(row.get("expected_decision") or "verbatim"),
                tags=list(row.get("tags") or []),
                is_active=True,
            )
        )
        count += 1
    await session.flush()
    return count
