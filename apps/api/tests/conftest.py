"""Shared pytest fixtures."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Ensure test env before settings import.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault(
    "SECRET_KEY", "test-secret-key-not-for-production-use-only-testing-1234567890"
)
os.environ.setdefault("ENCRYPTION_KEY", "dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcysh")
os.environ.setdefault("BOOTSTRAP_ADMIN_EMAIL", "admin@example.com")
os.environ.setdefault("BOOTSTRAP_ADMIN_PASSWORD", "ChangeMeNow123!")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("SEED_DEMO_DATA", "false")
os.environ.setdefault("POSTGRES_HOST", os.environ.get("POSTGRES_HOST", "localhost"))
os.environ.setdefault("POSTGRES_PORT", os.environ.get("POSTGRES_PORT", "5432"))
os.environ.setdefault("POSTGRES_USER", "amakuru")
os.environ.setdefault("POSTGRES_PASSWORD", "change-me")
os.environ.setdefault("POSTGRES_DB", "amakuru")
os.environ.setdefault("REDIS_URL", os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
os.environ.setdefault("REQUIRE_2FA_FOR_APPROVERS", "false")

from amakuru.core.db import Base, dispose_engine  # noqa: E402
from amakuru.core.settings import clear_settings_cache, get_settings  # noqa: E402
from amakuru.main import create_app  # noqa: E402
from amakuru.modules.identity.models import (  # noqa: E402
    ROLE_TENANT_ADMIN,
    Membership,
    User,
)
from amakuru.modules.identity.service import create_user  # noqa: E402
from amakuru.modules.tenancy.models import Tenant  # noqa: E402


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture
async def engine():
    clear_settings_cache()
    settings = get_settings()
    eng = create_async_engine(settings.database_url, pool_pre_ping=True)
    yield eng
    await eng.dispose()
    await dispose_engine()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    clear_settings_cache()
    await dispose_engine()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await dispose_engine()


@pytest_asyncio.fixture
async def two_tenants(engine) -> dict[str, object]:
    """Create two isolated tenants and one user in each."""
    clear_settings_cache()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        t1 = Tenant(
            id=uuid.uuid4(),
            name="Tenant Alpha Demo",
            slug=f"alpha-{uuid.uuid4().hex[:8]}",
            is_demo=True,
            demo_label="DEMONSTRATION CONTENT ONLY",
        )
        t2 = Tenant(
            id=uuid.uuid4(),
            name="Tenant Beta Demo",
            slug=f"beta-{uuid.uuid4().hex[:8]}",
            is_demo=True,
            demo_label="DEMONSTRATION CONTENT ONLY",
        )
        session.add_all([t1, t2])
        await session.flush()

        u1 = await create_user(
            session,
            email=f"alpha-{uuid.uuid4().hex[:8]}@example.com",
            password="AlphaPassword123!",
            full_name="Alpha Admin",
        )
        u2 = await create_user(
            session,
            email=f"beta-{uuid.uuid4().hex[:8]}@example.com",
            password="BetaPassword123!",
            full_name="Beta Admin",
        )
        session.add_all(
            [
                Membership(
                    id=uuid.uuid4(),
                    tenant_id=t1.id,
                    user_id=u1.id,
                    role=ROLE_TENANT_ADMIN,
                ),
                Membership(
                    id=uuid.uuid4(),
                    tenant_id=t2.id,
                    user_id=u2.id,
                    role=ROLE_TENANT_ADMIN,
                ),
            ]
        )
        await session.flush()
        payload = {
            "t1": t1.id,
            "t2": t2.id,
            "u1": u1.id,
            "u2": u2.id,
            "u1_email": u1.email,
            "u2_email": u2.email,
            "u1_password": "AlphaPassword123!",
            "u2_password": "BetaPassword123!",
        }
    return payload


async def set_tenant_local(session: AsyncSession, tenant_id: uuid.UUID | None) -> None:
    if tenant_id is None:
        await session.execute(text("SELECT set_config('app.tenant_id', '', true)"))
    else:
        await session.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"),
            {"tid": str(tenant_id)},
        )


# Silence unused import warning for Base in type checkers
_ = (Base, User)
