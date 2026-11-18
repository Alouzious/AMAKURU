"""Cross-tenant isolation for knowledge endpoints."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from amakuru.modules.knowledge.models import Office
from tests.conftest import set_tenant_local


@pytest.mark.asyncio
async def test_knowledge_api_hides_other_tenant(
    client: AsyncClient, engine, two_tenants: dict[str, object]
) -> None:
    t1 = two_tenants["t1"]
    t2 = two_tenants["t2"]
    assert isinstance(t1, uuid.UUID) and isinstance(t2, uuid.UUID)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await set_tenant_local(session, t1)
        o1 = Office(
            id=uuid.uuid4(),
            tenant_id=t1,
            name="Alpha Registrar",
            email="a@example.com",
        )
        session.add(o1)
        await set_tenant_local(session, t2)
        o2 = Office(
            id=uuid.uuid4(),
            tenant_id=t2,
            name="Beta Registrar",
            email="b@example.com",
        )
        session.add(o2)
        await session.flush()
        o2_id = o2.id

    email = str(two_tenants["u1_email"])
    password = str(two_tenants["u1_password"])
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    csrf = login.json()["user"]["csrf_token"]

    listed = await client.get(f"/api/v1/tenants/{t1}/offices", headers={"X-CSRF-Token": csrf})
    assert listed.status_code == 200
    names = {o["name"] for o in listed.json()}
    assert "Alpha Registrar" in names
    assert "Beta Registrar" not in names

    # Cannot create office on other tenant
    forbidden = await client.post(
        f"/api/v1/tenants/{t2}/offices",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Hacked"},
    )
    assert forbidden.status_code == 403

    # RLS via app role
    async with factory() as session, session.begin():
        await session.execute(text("SET LOCAL ROLE amakuru_app"))
        await set_tenant_local(session, t1)
        result = await session.execute(text("SELECT id FROM offices WHERE id = :id"), {"id": o2_id})
        assert result.first() is None


@pytest.mark.asyncio
async def test_rls_blocks_cross_tenant_office_write(engine, two_tenants: dict[str, object]) -> None:
    t1 = two_tenants["t1"]
    t2 = two_tenants["t2"]
    assert isinstance(t1, uuid.UUID) and isinstance(t2, uuid.UUID)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await set_tenant_local(session, t2)
        office = Office(id=uuid.uuid4(), tenant_id=t2, name="Beta Only")
        session.add(office)
        await session.flush()
        office_id = office.id

    async with factory() as session, session.begin():
        await session.execute(text("SET LOCAL ROLE amakuru_app"))
        await set_tenant_local(session, t1)
        result = await session.execute(
            text("UPDATE offices SET name = 'Hacked' WHERE id = :id RETURNING id"),
            {"id": office_id},
        )
        assert result.first() is None
