"""Cross-tenant isolation for embeddings / ask."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.conftest import set_tenant_local


@pytest.mark.asyncio
async def test_embeddings_rls(engine, two_tenants: dict[str, object]) -> None:
    t1 = two_tenants["t1"]
    t2 = two_tenants["t2"]
    assert isinstance(t1, uuid.UUID) and isinstance(t2, uuid.UUID)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    dense = "[" + ",".join(["0.01"] * 1024) + "]"
    async with factory() as session, session.begin():
        await set_tenant_local(session, t2)
        emb_id = uuid.uuid4()
        await session.execute(
            text(
                """
                INSERT INTO embeddings
                  (id, tenant_id, source_type, source_id, model_id, model_version, dense)
                VALUES
                  (:id, :tenant_id, 'answer_version', :sid, 'test', '1', CAST(:dense AS vector))
                """
            ),
            {
                "id": str(emb_id),
                "tenant_id": str(t2),
                "sid": str(uuid.uuid4()),
                "dense": dense,
            },
        )

    async with factory() as session, session.begin():
        await session.execute(text("SET LOCAL ROLE amakuru_app"))
        await set_tenant_local(session, t1)
        result = await session.execute(
            text("SELECT id FROM embeddings WHERE id = :id"), {"id": str(emb_id)}
        )
        assert result.first() is None


@pytest.mark.asyncio
async def test_ask_other_tenant_forbidden(
    client: AsyncClient, two_tenants: dict[str, object]
) -> None:
    email = str(two_tenants["u1_email"])
    password = str(two_tenants["u1_password"])
    t2 = two_tenants["t2"]
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    csrf = login.json()["user"]["csrf_token"]
    resp = await client.post(
        f"/api/v1/tenants/{t2}/ask",
        headers={"X-CSRF-Token": csrf},
        json={"question": "hello"},
    )
    assert resp.status_code == 403
