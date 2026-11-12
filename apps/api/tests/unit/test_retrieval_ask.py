"""Retrieval ask API smoke test against demo seed."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from amakuru.modules.tenancy.models import Tenant
from amakuru.scripts.seed import run as seed_run


@pytest.mark.asyncio
async def test_ask_demo_welcome(client: AsyncClient, engine) -> None:
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

    # Ensure index is current
    idx = await client.post(f"/api/v1/tenants/{tenant_id}/index", headers={"X-CSRF-Token": csrf})
    assert idx.status_code == 200, idx.text
    assert idx.json()["indexed"] >= 1

    ask = await client.post(
        f"/api/v1/tenants/{tenant_id}/ask",
        headers={"X-CSRF-Token": csrf},
        json={"question": "What is this demo chatbot for?"},
    )
    assert ask.status_code == 200, ask.text
    body = ask.json()
    assert body["decision"] in {"verbatim", "compose"}
    assert body["reply"]
    assert "DEMONSTRATION" in body["reply"]
