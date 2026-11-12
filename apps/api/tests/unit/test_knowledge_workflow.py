"""Knowledge governance workflow tests."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pyotp
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from amakuru.core.settings import get_settings
from amakuru.modules.identity.models import ROLE_OFFICE_EDITOR, Membership
from amakuru.modules.identity.service import create_user
from amakuru.modules.knowledge.models import Office
from amakuru.modules.tenancy.models import Tenant
from amakuru.scripts.seed import run as seed_run


async def _login(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    csrf = resp.json()["user"]["csrf_token"]
    assert csrf
    return csrf


async def _enable_2fa(client: AsyncClient, csrf: str, engine) -> None:
    setup = await client.post("/api/v1/auth/2fa/setup", headers={"X-CSRF-Token": csrf})
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    code = pyotp.TOTP(secret).now()
    verify = await client.post(
        "/api/v1/auth/2fa/verify",
        headers={"X-CSRF-Token": csrf},
        json={"code": code},
    )
    assert verify.status_code == 200, verify.text


@pytest.mark.asyncio
async def test_editor_submit_approver_publish(client: AsyncClient, engine) -> None:
    settings = get_settings()
    # Force 2FA requirement for this test path via settings already true by default;
    # seed creates users without 2FA — we enable for approver.
    await seed_run()

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == "demo-university"))
        ).scalar_one()
        office = (
            await session.execute(
                select(Office).where(Office.tenant_id == tenant.id, Office.name == "Registrar")
            )
        ).scalar_one()
        tenant_id = tenant.id
        office_id = office.id

    editor_csrf = await _login(client, "editor@example.com", "ChangeMeNow123!")
    create = await client.post(
        f"/api/v1/tenants/{tenant_id}/answer-entries",
        headers={"X-CSRF-Token": editor_csrf},
        json={
            "office_id": str(office_id),
            "category": "demo",
            "subcategory": "workflow",
            "answer_text": "DEMONSTRATION ONLY: workflow answer.",
            "valid_until": str(date.today() + timedelta(days=60)),
            "question_raw": "How does the demo workflow work?",
        },
    )
    assert create.status_code == 200, create.text
    entry = create.json()
    version_id = entry["latest_version"]["id"]

    submit = await client.post(
        f"/api/v1/tenants/{tenant_id}/versions/{version_id}/submit",
        headers={"X-CSRF-Token": editor_csrf},
    )
    assert submit.status_code == 200, submit.text
    assert submit.json()["status"] == "in_review"

    # Editor cannot approve own version
    self_approve = await client.post(
        f"/api/v1/tenants/{tenant_id}/versions/{version_id}/approve",
        headers={"X-CSRF-Token": editor_csrf},
    )
    assert self_approve.status_code == 403

    # Approver without 2FA rejected when required
    await client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": editor_csrf})
    approver_csrf = await _login(client, "approver@example.com", "ChangeMeNow123!")
    if settings.require_2fa_for_approvers:
        no_2fa = await client.post(
            f"/api/v1/tenants/{tenant_id}/versions/{version_id}/approve",
            headers={"X-CSRF-Token": approver_csrf},
        )
        assert no_2fa.status_code == 403
        await _enable_2fa(client, approver_csrf, engine)
        # Re-login so session picks up totp_enabled from DB on next requests —
        # approve path loads user from DB each request, so OK without re-login.
        # But CSRF still valid.

    approve = await client.post(
        f"/api/v1/tenants/{tenant_id}/versions/{version_id}/approve",
        headers={"X-CSRF-Token": approver_csrf},
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["status"] == "approved"

    publish = await client.post(
        f"/api/v1/tenants/{tenant_id}/versions/{version_id}/publish",
        headers={"X-CSRF-Token": approver_csrf},
    )
    assert publish.status_code == 200, publish.text
    assert publish.json()["status"] == "published"


@pytest.mark.asyncio
async def test_cross_office_editor_forbidden(client: AsyncClient, engine) -> None:
    await seed_run()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == "demo-university"))
        ).scalar_one()
        finance = (
            await session.execute(
                select(Office).where(Office.tenant_id == tenant.id, Office.name == "Finance")
            )
        ).scalar_one()
        other = await create_user(
            session,
            email=f"other-editor-{uuid.uuid4().hex[:8]}@example.com",
            password="ChangeMeNow123!",
            full_name="Other Editor",
        )
        session.add(
            Membership(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                user_id=other.id,
                role=ROLE_OFFICE_EDITOR,
                office_id=finance.id,
            )
        )
        await session.flush()
        email = other.email
        tenant_id = tenant.id
        registrar_id = (
            (
                await session.execute(
                    select(Office).where(Office.tenant_id == tenant.id, Office.name == "Registrar")
                )
            )
            .scalar_one()
            .id
        )

    csrf = await _login(client, email, "ChangeMeNow123!")
    resp = await client.post(
        f"/api/v1/tenants/{tenant_id}/answer-entries",
        headers={"X-CSRF-Token": csrf},
        json={
            "office_id": str(registrar_id),
            "category": "demo",
            "subcategory": "forbidden",
            "answer_text": "should fail",
        },
    )
    assert resp.status_code == 403
