"""Hand-off packaging and unanswered queue."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from amakuru.modules.channels.models import UnansweredItem
from amakuru.modules.knowledge.models import Office


async def load_office(
    session: AsyncSession, *, tenant_id: uuid.UUID, office_id: uuid.UUID | None
) -> Office | None:
    if office_id is None:
        # Fall back to first office for the tenant
        result = await session.execute(
            select(Office)
            .where(Office.tenant_id == tenant_id, Office.deleted_at.is_(None))
            .order_by(Office.created_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()
    result = await session.execute(
        select(Office).where(
            Office.tenant_id == tenant_id,
            Office.id == office_id,
            Office.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


def handoff_card(office: Office | None, *, reply: str) -> dict[str, Any]:
    if office is None:
        return {
            "title": "Talk to a person",
            "body": reply,
            "office_name": None,
            "contact_person": None,
            "phone": None,
            "email": None,
            "opening_hours": None,
        }
    return {
        "title": "Talk to a person",
        "body": reply,
        "office_name": office.name,
        "contact_person": office.contact_person,
        "phone": office.phone,
        "email": office.email,
        "opening_hours": office.opening_hours,
    }


async def enqueue_unanswered(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    question: str,
    language: str,
    channel: str,
    office_id: uuid.UUID | None,
    conversation_id: uuid.UUID | None,
    trace_id: uuid.UUID | None,
) -> uuid.UUID:
    # Simple exact-match clustering for Phase 4
    existing = await session.execute(
        select(UnansweredItem).where(
            UnansweredItem.tenant_id == tenant_id,
            UnansweredItem.status == "open",
            UnansweredItem.question == question,
        )
    )
    row = existing.scalar_one_or_none()
    if row is not None:
        row.count += 1
        await session.flush()
        return row.id
    item = UnansweredItem(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        question=question,
        language=language,
        channel=channel,
        office_id=office_id,
        conversation_id=conversation_id,
        trace_id=trace_id,
        count=1,
        status="open",
    )
    session.add(item)
    await session.flush()
    return item.id
