"""Live search intelligence: every asked question is remembered and clustered.

This is Amakuru's side of 'knowing what people search'. University DBs can still
be pulled via sql_db / rest_json connectors; widget/WhatsApp questions land here.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from amakuru.modules.knowledge.models import NeedsAnswerItem, Office, SearchEvent
from amakuru.modules.knowledge.service import create_draft_from_mapped_row
from amakuru.modules.platform.audit import write_audit


def normalize_question(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text.strip().lower())
    return cleaned[:2000]


async def record_search(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    question: str,
    language: str,
    channel: str,
    decision: str,
    answered: bool,
    conversation_id: uuid.UUID | None = None,
    trace_id: uuid.UUID | None = None,
) -> uuid.UUID:
    norm = normalize_question(question)
    if not norm:
        return uuid.uuid4()

    existing = await session.execute(
        select(SearchEvent).where(
            SearchEvent.tenant_id == tenant_id,
            SearchEvent.normalized_question == norm,
        )
    )
    row = existing.scalar_one_or_none()
    now = datetime.now(UTC)
    if row is not None:
        row.count += 1
        row.last_asked_at = now
        row.language = language or row.language
        row.channel = channel or row.channel
        row.decision = decision
        row.answered = answered or row.answered
        if conversation_id:
            row.last_conversation_id = conversation_id
        if trace_id:
            row.last_trace_id = trace_id
        await session.flush()
        event_id = row.id
    else:
        event = SearchEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            question=question.strip()[:4000],
            normalized_question=norm,
            language=language or "en",
            channel=channel or "widget",
            decision=decision,
            answered=answered,
            count=1,
            last_asked_at=now,
            last_conversation_id=conversation_id,
            last_trace_id=trace_id,
        )
        session.add(event)
        await session.flush()
        event_id = event.id

    return event_id


async def promote_hot_searches_to_drafts(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    min_count: int = 3,
    limit: int = 50,
) -> dict[str, Any]:
    """Turn frequent unanswered searches into needs-answer / draft stubs for offices."""
    result = await session.execute(
        select(SearchEvent)
        .where(
            SearchEvent.tenant_id == tenant_id,
            SearchEvent.answered.is_(False),
            SearchEvent.count >= min_count,
            SearchEvent.promoted.is_(False),
        )
        .order_by(SearchEvent.count.desc())
        .limit(limit)
    )
    events = list(result.scalars().all())
    office = (
        await session.execute(
            select(Office)
            .where(Office.tenant_id == tenant_id, Office.deleted_at.is_(None))
            .order_by(Office.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()

    created = 0
    for event in events:
        # Avoid duplicate open needs-answer rows
        dup = await session.execute(
            select(NeedsAnswerItem).where(
                NeedsAnswerItem.tenant_id == tenant_id,
                NeedsAnswerItem.question_raw == event.question,
                NeedsAnswerItem.status == "open",
            )
        )
        if dup.scalar_one_or_none() is not None:
            event.promoted = True
            continue

        kind, _id = await create_draft_from_mapped_row(
            session,
            tenant_id=tenant_id,
            mapped={
                "question_raw": event.question,
                "official_answer": "",
                "language": event.language,
                "channel": event.channel,
                "category": "live_search",
                "subcategory": "hot",
                "frequency": str(event.count),
                "owner_office": office.name if office else "",
            },
            actor_id=actor_id,
            default_office_id=office.id if office else None,
        )
        if kind in {"needs_answer", "entry"}:
            created += 1
            event.promoted = True

    await write_audit(
        session,
        action="search.promote",
        resource_type="search_events",
        resource_id=str(tenant_id),
        tenant_id=tenant_id,
        actor_user_id=actor_id,
        detail={"created": created, "scanned": len(events)},
    )
    return {"created": created, "scanned": len(events)}
