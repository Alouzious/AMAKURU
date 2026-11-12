"""Central entitlement and quota checks."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from amakuru.core.errors import ForbiddenError, QuotaExceededError
from amakuru.modules.billing.catalog import (
    ENT_API_ACCESS,
    ENT_MAX_PUBLISHED,
    ENT_MONTHLY_CONVERSATIONS,
    ENT_WHATSAPP,
    ENT_WHITE_LABEL,
    entitlements_for,
)
from amakuru.modules.billing.models import UsageEvent
from amakuru.modules.knowledge.models import STATUS_PUBLISHED, AnswerEntry, AnswerVersion
from amakuru.modules.tenancy.models import Tenant


async def load_tenant_plan(session: AsyncSession, tenant_id: UUID) -> tuple[Tenant, dict[str, Any]]:
    result = await session.execute(
        select(Tenant).where(Tenant.id == tenant_id, Tenant.deleted_at.is_(None))
    )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise ForbiddenError("Tenant not found")
    return tenant, entitlements_for(tenant.plan)


def require_bool(ents: dict[str, Any], key: str, *, feature: str) -> None:
    if not bool(ents.get(key)):
        raise ForbiddenError(f"Plan does not include {feature}. Upgrade to unlock.")


async def require_api_access(session: AsyncSession, tenant_id: UUID) -> None:
    _, ents = await load_tenant_plan(session, tenant_id)
    require_bool(ents, ENT_API_ACCESS, feature="API access")


async def require_whatsapp(session: AsyncSession, tenant_id: UUID) -> None:
    _, ents = await load_tenant_plan(session, tenant_id)
    require_bool(ents, ENT_WHATSAPP, feature="WhatsApp")


async def require_white_label(session: AsyncSession, tenant_id: UUID) -> None:
    _, ents = await load_tenant_plan(session, tenant_id)
    require_bool(ents, ENT_WHITE_LABEL, feature="white-labelling")


async def count_published_entries(session: AsyncSession, tenant_id: UUID) -> int:
    q = await session.execute(
        select(func.count(func.distinct(AnswerEntry.id)))
        .join(AnswerVersion, AnswerVersion.entry_id == AnswerEntry.id)
        .where(
            AnswerEntry.tenant_id == tenant_id,
            AnswerEntry.deleted_at.is_(None),
            AnswerVersion.status == STATUS_PUBLISHED,
        )
    )
    return int(q.scalar_one() or 0)


async def assert_can_publish(session: AsyncSession, tenant_id: UUID) -> None:
    _, ents = await load_tenant_plan(session, tenant_id)
    limit = int(ents.get(ENT_MAX_PUBLISHED) or 0)
    current = await count_published_entries(session, tenant_id)
    if current >= limit:
        raise QuotaExceededError(
            f"Published answer limit reached ({current}/{limit}). Upgrade plan or archive entries."
        )


def _month_start(today: date | None = None) -> date:
    d = today or datetime.now(UTC).date()
    return date(d.year, d.month, 1)


async def monthly_answered_count(session: AsyncSession, tenant_id: UUID) -> int:
    start = _month_start()
    q = await session.execute(
        select(func.coalesce(func.sum(UsageEvent.quantity), 0)).where(
            UsageEvent.tenant_id == tenant_id,
            UsageEvent.event_type == "answered_conversation",
            UsageEvent.day >= start,
        )
    )
    return int(q.scalar_one() or 0)


async def assert_conversation_quota(session: AsyncSession, tenant_id: UUID) -> None:
    _, ents = await load_tenant_plan(session, tenant_id)
    limit = int(ents.get(ENT_MONTHLY_CONVERSATIONS) or 0)
    used = await monthly_answered_count(session, tenant_id)
    if used >= limit:
        raise QuotaExceededError(
            f"Monthly answered conversation quota reached ({used}/{limit}). "
            "Contact your Amakuru account manager or upgrade plan."
        )


async def usage_snapshot(session: AsyncSession, tenant_id: UUID) -> dict[str, Any]:
    tenant, ents = await load_tenant_plan(session, tenant_id)
    published = await count_published_entries(session, tenant_id)
    answered = await monthly_answered_count(session, tenant_id)
    return {
        "plan": tenant.plan,
        "entitlements": ents,
        "usage": {
            "published_answers": published,
            "published_answers_limit": int(ents.get(ENT_MAX_PUBLISHED) or 0),
            "answered_conversations_month": answered,
            "answered_conversations_limit": int(ents.get(ENT_MONTHLY_CONVERSATIONS) or 0),
        },
    }
