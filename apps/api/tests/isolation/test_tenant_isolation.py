"""Cross-tenant isolation suite — must find nothing across tenants."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from amakuru.modules.identity.models import Membership
from amakuru.modules.tenancy.models import Tenant
from tests.conftest import set_tenant_local


async def _as_app_role(session) -> None:  # type: ignore[no-untyped-def]
    """Switch to amakuru_app so RLS is enforced (superusers bypass RLS)."""
    await session.execute(text("SET LOCAL ROLE amakuru_app"))


@pytest.mark.asyncio
async def test_rls_hides_other_tenant(engine, two_tenants: dict[str, object]) -> None:
    t1 = two_tenants["t1"]
    t2 = two_tenants["t2"]
    assert isinstance(t1, uuid.UUID) and isinstance(t2, uuid.UUID)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await _as_app_role(session)
        await set_tenant_local(session, t1)
        result = await session.execute(select(Tenant).where(Tenant.id == t2))
        assert result.scalar_one_or_none() is None

        result_own = await session.execute(select(Tenant).where(Tenant.id == t1))
        assert result_own.scalar_one_or_none() is not None

        mem_other = await session.execute(select(Membership).where(Membership.tenant_id == t2))
        assert mem_other.scalars().all() == []


@pytest.mark.asyncio
async def test_rls_blocks_cross_tenant_write(engine, two_tenants: dict[str, object]) -> None:
    t1 = two_tenants["t1"]
    t2 = two_tenants["t2"]
    assert isinstance(t1, uuid.UUID) and isinstance(t2, uuid.UUID)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await _as_app_role(session)
        await set_tenant_local(session, t1)
        # Attempt to update the other tenant's name while scoped to t1.
        result = await session.execute(
            text("UPDATE tenants SET name = 'Hacked' WHERE id = :id RETURNING id"),
            {"id": t2},
        )
        assert result.first() is None


@pytest.mark.asyncio
async def test_api_user_cannot_read_other_tenant(
    client: AsyncClient, two_tenants: dict[str, object]
) -> None:
    email = str(two_tenants["u1_email"])
    password = str(two_tenants["u1_password"])
    t2 = two_tenants["t2"]

    login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200

    # List should only include tenant 1.
    listed = await client.get("/api/v1/tenants")
    assert listed.status_code == 200
    ids = {row["id"] for row in listed.json()}
    assert str(two_tenants["t1"]) in ids
    assert str(t2) not in ids

    # Direct fetch of other tenant must be forbidden.
    other = await client.get(f"/api/v1/tenants/{t2}")
    assert other.status_code == 403


@pytest.mark.asyncio
async def test_empty_tenant_context_still_scoped_by_api(
    client: AsyncClient, two_tenants: dict[str, object]
) -> None:
    """Unauthenticated access to tenant routes must fail."""
    t1 = two_tenants["t1"]
    resp = await client.get(f"/api/v1/tenants/{t1}")
    assert resp.status_code == 401
