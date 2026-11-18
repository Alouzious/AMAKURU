"""Expiry reminders and automatic unpublish."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from amakuru.core.db import set_tenant
from amakuru.core.logging import get_logger
from amakuru.modules.knowledge.models import (
    STATUS_EXPIRED,
    STATUS_PUBLISHED,
    AnswerEntry,
    AnswerVersion,
    Office,
)
from amakuru.modules.platform.audit import write_audit
from amakuru.modules.tenancy.models import Tenant

logger = get_logger("amakuru.expiry")

REMINDER_DAYS = (30, 14, 3)


async def unpublish_expired(session: AsyncSession, *, tenant_id: UUID | None = None) -> int:
    today = date.today()
    q = select(AnswerVersion).where(
        AnswerVersion.status == STATUS_PUBLISHED,
        AnswerVersion.valid_until.is_not(None),
        AnswerVersion.valid_until < today,
    )
    if tenant_id is not None:
        q = q.where(AnswerVersion.tenant_id == tenant_id)
    result = await session.execute(q)
    versions = list(result.scalars().all())
    for version in versions:
        version.status = STATUS_EXPIRED
        await write_audit(
            session,
            action="answer.expire",
            resource_type="answer_version",
            resource_id=str(version.id),
            tenant_id=version.tenant_id,
            detail={"valid_until": str(version.valid_until)},
        )
        logger.info(
            "version_expired",
            version_id=str(version.id),
            tenant_id=str(version.tenant_id),
        )
    return len(versions)


async def send_expiry_reminders(session: AsyncSession) -> list[dict[str, Any]]:
    """Mark and return reminder events for published versions nearing expiry."""
    today = date.today()
    sent: list[dict[str, Any]] = []
    result = await session.execute(
        select(AnswerVersion, AnswerEntry, Office)
        .join(AnswerEntry, AnswerEntry.id == AnswerVersion.entry_id)
        .join(Office, Office.id == AnswerEntry.office_id)
        .where(AnswerVersion.status == STATUS_PUBLISHED, AnswerVersion.valid_until.is_not(None))
    )
    for version, entry, office in result.all():
        assert version.valid_until is not None
        days_left = (version.valid_until - today).days
        for window in REMINDER_DAYS:
            if days_left != window:
                continue
            field = f"reminder_{window}_sent_at"
            if getattr(version, field) is not None:
                continue
            setattr(version, field, datetime.now(UTC))
            event = {
                "tenant_id": str(version.tenant_id),
                "version_id": str(version.id),
                "entry_id": str(entry.id),
                "office_email": office.email,
                "office_name": office.name,
                "days_left": window,
                "valid_until": str(version.valid_until),
            }
            sent.append(event)
            await write_audit(
                session,
                action=f"answer.reminder_{window}",
                resource_type="answer_version",
                resource_id=str(version.id),
                tenant_id=version.tenant_id,
                detail=event,
            )
            logger.info("expiry_reminder", **event)
    return sent


async def run_expiry_jobs(factory: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    """Run unpublish + reminders across all tenants (platform connection)."""
    async with factory() as session, session.begin():
        await set_tenant(session, None)
        tenants = (
            await session.execute(select(Tenant).where(Tenant.deleted_at.is_(None)))
        ).scalars()
        expired_total = 0
        for tenant in tenants:
            await set_tenant(session, tenant.id)
            expired_total += await unpublish_expired(session, tenant_id=tenant.id)
        await set_tenant(session, None)
        reminders = await send_expiry_reminders(session)
        return {"expired": expired_total, "reminders": len(reminders), "reminder_events": reminders}


def versions_due_for_reminder(
    versions: list[AnswerVersion], *, today: date | None = None
) -> list[tuple[AnswerVersion, int]]:
    """Pure helper for unit tests."""
    today = today or date.today()
    due: list[tuple[AnswerVersion, int]] = []
    for version in versions:
        if version.valid_until is None or version.status != STATUS_PUBLISHED:
            continue
        days_left = (version.valid_until - today).days
        for window in REMINDER_DAYS:
            if days_left != window:
                continue
            already = getattr(version, f"reminder_{window}_sent_at")
            if already is None:
                due.append((version, window))
    return due


def is_expired(version: AnswerVersion, *, today: date | None = None) -> bool:
    today = today or date.today()
    return (
        version.status == STATUS_PUBLISHED
        and version.valid_until is not None
        and version.valid_until < today
    )


# Keep timedelta import used in docs/tests
_ = timedelta
