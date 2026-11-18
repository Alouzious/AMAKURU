"""Commercial APIs: plans, onboarding, billing, API keys, isolation."""

from __future__ import annotations

import os
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from amakuru.core.settings import clear_settings_cache
from amakuru.modules.billing.keys import hash_api_key
from amakuru.modules.billing.models import ApiKey
from amakuru.modules.identity.models import ROLE_TENANT_ADMIN, Membership
from amakuru.modules.identity.service import create_user
from amakuru.modules.tenancy.models import Tenant
from amakuru.scripts.seed import DEMO_B_SLUG, DEMO_SLUG
from amakuru.scripts.seed import run as seed_run
from tests.conftest import set_tenant_local


async def _seed_demos() -> None:
    os.environ["SEED_DEMO_DATA"] = "true"
    clear_settings_cache()
    await seed_run()
    clear_settings_cache()


async def _login(client: AsyncClient, email: str, password: str) -> str:
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["user"]["csrf_token"]


@pytest.mark.asyncio
async def test_list_plans(client: AsyncClient) -> None:
    res = await client.get("/api/v1/plans")
    assert res.status_code == 200
    codes = {p["code"] for p in res.json()}
    assert codes == {"starter", "campus", "enterprise"}


@pytest.mark.asyncio
async def test_second_demo_tenant_seeded_and_isolated(client: AsyncClient, engine) -> None:
    await _seed_demos()
    csrf = await _login(client, "admin@example.com", "ChangeMeNow123!")

    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200
    memberships = me.json()["memberships"]
    by_slug = {m["tenant_slug"]: m for m in memberships}
    assert DEMO_SLUG in by_slug
    assert DEMO_B_SLUG in by_slug
    uni_id = by_slug[DEMO_SLUG]["tenant_id"]
    college_id = by_slug[DEMO_B_SLUG]["tenant_id"]

    uni_entries = await client.get(
        f"/api/v1/tenants/{uni_id}/answer-entries",
        headers={"X-CSRF-Token": csrf},
    )
    college_entries = await client.get(
        f"/api/v1/tenants/{college_id}/answer-entries",
        headers={"X-CSRF-Token": csrf},
    )
    assert uni_entries.status_code == 200
    assert college_entries.status_code == 200
    uni_subs = {e.get("subcategory") for e in uni_entries.json()}
    college_subs = {e.get("subcategory") for e in college_entries.json()}
    assert "college-welcome" not in uni_subs
    assert "college-welcome" in college_subs
    assert "welcome" not in college_subs or "welcome" in uni_subs


@pytest.mark.asyncio
async def test_onboarding_creates_tenant(client: AsyncClient) -> None:
    await _seed_demos()
    csrf = await _login(client, "admin@example.com", "ChangeMeNow123!")
    slug = f"onboard-{uuid.uuid4().hex[:8]}"
    res = await client.post(
        "/api/v1/onboarding",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "Onboard Demo University",
            "slug": slug,
            "plan": "campus",
            "accent": "#123456",
            "admin_email": f"admin-{slug}@example.com",
            "admin_full_name": "Onboard Admin",
            "admin_password": "ChangeMeNow123!",
            "seed_demo_answers": True,
            "is_demo": True,
            "offices": [{"name": "Registrar"}],
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["slug"] == slug
    assert body["widget_key"].startswith("ak_live_")
    assert "amakuru-widget.js" in body["embed_snippet"]

    billing = await client.get(
        f"/api/v1/tenants/{body['tenant_id']}/billing",
        headers={"X-CSRF-Token": csrf},
    )
    assert billing.status_code == 200
    assert billing.json()["plan"] == "campus"


@pytest.mark.asyncio
async def test_api_key_requires_campus_and_isolates(client: AsyncClient, engine) -> None:
    await _seed_demos()
    csrf = await _login(client, "admin@example.com", "ChangeMeNow123!")
    me = (await client.get("/api/v1/auth/me")).json()
    by_slug = {m["tenant_slug"]: m for m in me["memberships"]}
    starter_id = by_slug[DEMO_SLUG]["tenant_id"]
    campus_id = by_slug[DEMO_B_SLUG]["tenant_id"]

    denied = await client.post(
        f"/api/v1/tenants/{starter_id}/api-keys",
        headers={"X-CSRF-Token": csrf},
        json={"name": "blocked", "scopes": ["ask"]},
    )
    assert denied.status_code == 403

    created = await client.post(
        f"/api/v1/tenants/{campus_id}/api-keys",
        headers={"X-CSRF-Token": csrf},
        json={"name": "college-api", "scopes": ["ask"]},
    )
    assert created.status_code == 200, created.text
    raw = created.json()["raw_key"]
    assert raw.startswith("ak_api_")

    ask = await client.post(
        "/api/v1/external/ask",
        headers={"Authorization": f"Bearer {raw}"},
        json={"question": "What is Demo College's chatbot for?", "language": "en"},
    )
    assert ask.status_code == 200, ask.text
    assert "Demo College" in ask.json()["reply"] or "demonstration" in ask.json()["reply"].lower()

    # Key hash must not be readable under the other tenant RLS context
    # (superuser bypasses RLS — switch to amakuru_app like isolation suite)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await session.execute(text("SET LOCAL ROLE amakuru_app"))
        await set_tenant_local(session, uuid.UUID(starter_id))
        found = await session.execute(select(ApiKey).where(ApiKey.key_hash == hash_api_key(raw)))
        assert found.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_billing_summary_for_member(client: AsyncClient, engine) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        tenant = Tenant(
            id=uuid.uuid4(),
            name="Billing Demo",
            slug=f"bill-{uuid.uuid4().hex[:8]}",
            plan="enterprise",
            is_demo=True,
            demo_label="DEMONSTRATION",
            branding={"accent": "#000000", "display_name": "Billing Demo"},
        )
        session.add(tenant)
        await session.flush()
        user = await create_user(
            session,
            email=f"bill-{uuid.uuid4().hex[:6]}@example.com",
            password="ChangeMeNow123!",
            full_name="Bill Admin",
        )
        session.add(
            Membership(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                user_id=user.id,
                role=ROLE_TENANT_ADMIN,
            )
        )
        email = user.email
        tid = str(tenant.id)

    csrf = await _login(client, email, "ChangeMeNow123!")
    res = await client.get(f"/api/v1/tenants/{tid}/billing", headers={"X-CSRF-Token": csrf})
    assert res.status_code == 200
    body = res.json()
    assert body["plan"] == "enterprise"
    assert body["entitlements"]["white_label"] is True
    assert body["usage"]["published_answers_limit"] == 10_000
