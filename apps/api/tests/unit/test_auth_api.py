"""Auth API smoke tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from amakuru.core.settings import get_settings
from amakuru.scripts.seed import run as seed_run


@pytest.mark.asyncio
async def test_login_me_logout(client: AsyncClient) -> None:
    await seed_run()
    settings = get_settings()

    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": settings.bootstrap_admin_email,
            "password": settings.bootstrap_admin_password,
        },
    )
    assert login.status_code == 200, login.text
    body = login.json()
    assert body["user"]["email"] == settings.bootstrap_admin_email
    assert body["user"]["is_platform_admin"] is True
    csrf = body["user"]["csrf_token"]
    assert csrf

    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == settings.bootstrap_admin_email

    logout = await client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    assert logout.status_code == 200

    me2 = await client.get("/api/v1/auth/me")
    assert me2.status_code == 401


@pytest.mark.asyncio
async def test_health(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
