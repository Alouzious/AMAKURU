"""Phase 5 analytics / dashboard API smoke tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from amakuru.modules.tenancy.models import Tenant
from amakuru.scripts.seed import run as seed_run


@pytest.mark.asyncio
async def test_overview_and_channel_config(client: AsyncClient, engine) -> None:
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

    overview = await client.get(f"/api/v1/tenants/{tenant_id}/overview")
    assert overview.status_code == 200, overview.text
    body = overview.json()
    assert "answered_share" in body
    assert "published_entries" in body

    channels = await client.get(f"/api/v1/tenants/{tenant_id}/channel-config")
    assert channels.status_code == 200
    assert channels.json()["widget_key_prefix"]

    team = await client.get(f"/api/v1/tenants/{tenant_id}/team")
    assert team.status_code == 200
    assert len(team.json()) >= 1

    audit = await client.get(f"/api/v1/tenants/{tenant_id}/audit-log")
    assert audit.status_code == 200

    # CSRF-protected eval trigger
    eval_res = await client.post(
        f"/api/v1/tenants/{tenant_id}/eval-runs",
        headers={"X-CSRF-Token": csrf},
    )
    assert eval_res.status_code == 200, eval_res.text
    assert "metrics" in eval_res.json()
