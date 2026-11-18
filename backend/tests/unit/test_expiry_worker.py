"""Expiry and reminder unit tests."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from amakuru.core.db import set_tenant
from amakuru.modules.identity.service import create_user
from amakuru.modules.knowledge.expiry import (
    is_expired,
    send_expiry_reminders,
    unpublish_expired,
    versions_due_for_reminder,
)
from amakuru.modules.knowledge.models import (
    STATUS_PUBLISHED,
    AnswerEntry,
    AnswerVersion,
    Office,
)
from amakuru.modules.tenancy.models import Tenant
from amakuru.scripts.seed import run as seed_run


def test_versions_due_for_reminder_windows() -> None:
    today = date(2026, 6, 1)
    v30 = AnswerVersion(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        entry_id=uuid.uuid4(),
        version_number=1,
        answer_text="x",
        status=STATUS_PUBLISHED,
        editor_id=uuid.uuid4(),
        valid_until=today + timedelta(days=30),
    )
    due = versions_due_for_reminder([v30], today=today)
    assert due == [(v30, 30)]
    assert is_expired(v30, today=today) is False
    v30.valid_until = today - timedelta(days=1)
    assert is_expired(v30, today=today) is True


@pytest.mark.asyncio
async def test_unpublish_and_reminders(engine) -> None:
    await seed_run()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == "demo-university"))
        ).scalar_one()
        await set_tenant(session, tenant.id)
        office = (
            await session.execute(
                select(Office).where(Office.tenant_id == tenant.id, Office.name == "Registrar")
            )
        ).scalar_one()
        editor = await create_user(
            session,
            email=f"expiry-editor-{uuid.uuid4().hex[:8]}@example.com",
            password="ChangeMeNow123!",
            full_name="Expiry Editor",
        )
        entry = AnswerEntry(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            office_id=office.id,
            category="demo",
            subcategory="expiry",
        )
        session.add(entry)
        await session.flush()
        expired = AnswerVersion(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            entry_id=entry.id,
            version_number=1,
            answer_text="DEMONSTRATION ONLY expired",
            status=STATUS_PUBLISHED,
            editor_id=editor.id,
            valid_until=date.today() - timedelta(days=1),
        )
        soon = AnswerVersion(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            entry_id=entry.id,
            version_number=2,
            answer_text="DEMONSTRATION ONLY soon",
            status=STATUS_PUBLISHED,
            editor_id=editor.id,
            valid_until=date.today() + timedelta(days=14),
        )
        session.add_all([expired, soon])
        await session.flush()
        expired_id = expired.id
        soon_id = soon.id

        count = await unpublish_expired(session, tenant_id=tenant.id)
        assert count >= 1
        await session.refresh(expired)
        assert expired.status == "expired"

        reminders = await send_expiry_reminders(session)
        assert any(r["version_id"] == str(soon_id) and r["days_left"] == 14 for r in reminders)
        await session.refresh(soon)
        assert soon.reminder_14_sent_at is not None
        # Idempotent
        again = await send_expiry_reminders(session)
        assert not any(r["version_id"] == str(soon_id) for r in again)
        _ = expired_id
