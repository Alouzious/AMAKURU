"""Import and mapping tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from amakuru.modules.knowledge.importing import preview_import, suggest_mapping
from amakuru.modules.knowledge.models import AnswerEntry, NeedsAnswerItem
from amakuru.modules.tenancy.models import Tenant
from amakuru.scripts.seed import run as seed_run

FIXTURE = Path(__file__).resolve().parents[4] / "eval" / "fixtures" / "club_dataset_sample.csv"


def test_suggest_mapping_club_headers() -> None:
    headers = [
        "question_raw",
        "official_answer",
        "owner_office",
        "category",
        "extra",
    ]
    mapping = suggest_mapping(headers)
    assert mapping["question_raw"] == "question_raw"
    assert mapping["official_answer"] == "official_answer"
    assert mapping["owner_office"] == "owner_office"
    assert "extra" not in mapping.values() or "extra" not in mapping


def test_preview_club_fixture() -> None:
    content = FIXTURE.read_bytes()
    preview = preview_import(content, "club_dataset_sample.csv")
    assert preview.row_count == 3
    assert "question_raw" in preview.suggested_mapping
    assert "official_answer" in preview.suggested_mapping


@pytest.mark.asyncio
async def test_import_run_creates_drafts_and_needs_answer(client: AsyncClient, engine) -> None:
    await seed_run()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == "demo-university"))
        ).scalar_one()
        tenant_id = tenant.id

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "ChangeMeNow123!"},
    )
    assert login.status_code == 200
    csrf = login.json()["user"]["csrf_token"]

    content = FIXTURE.read_bytes()
    preview = preview_import(content, "club_dataset_sample.csv")
    import json

    resp = await client.post(
        f"/api/v1/tenants/{tenant_id}/imports/run",
        headers={"X-CSRF-Token": csrf},
        files={"file": ("club_dataset_sample.csv", content, "text/csv")},
        data={"mapping_json": json.dumps(preview.suggested_mapping)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created_entries"] == 2
    assert body["needs_answer"] == 1

    async with factory() as session:
        from amakuru.core.db import set_tenant

        await set_tenant(session, tenant_id)
        entries = (
            (
                await session.execute(
                    select(AnswerEntry).where(
                        AnswerEntry.tenant_id == tenant_id, AnswerEntry.category == "demo"
                    )
                )
            )
            .scalars()
            .all()
        )
        needs = (
            (
                await session.execute(
                    select(NeedsAnswerItem).where(
                        NeedsAnswerItem.tenant_id == tenant_id, NeedsAnswerItem.status == "open"
                    )
                )
            )
            .scalars()
            .all()
        )
        # At least the imported drafts (plus possible seed welcome draft)
        assert len(entries) >= 2
        assert any("fictional demo fees" in n.question_raw.lower() for n in needs)
