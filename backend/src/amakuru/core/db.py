"""Async SQLAlchemy engine, sessions, and tenant-scoped transactions."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from amakuru.core.settings import Settings, get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


class Base(DeclarativeBase):
    pass


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    global _engine, _session_factory
    if _engine is None:
        settings = settings or get_settings()
        url = settings.app_database_url if settings.use_app_role else settings.database_url
        _engine = create_async_engine(
            url,
            pool_pre_ping=True,
            echo=settings.app_env == "development",
        )
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_session_factory(settings: Settings | None = None) -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        get_engine(settings)
    assert _session_factory is not None
    return _session_factory


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def get_db() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


@asynccontextmanager
async def tenant_session(
    tenant_id: UUID | None,
    *,
    settings: Settings | None = None,
) -> AsyncIterator[AsyncSession]:
    """Open a transaction and set app.tenant_id for RLS policies."""
    factory = get_session_factory(settings)
    async with factory() as session, session.begin():
        if tenant_id is not None:
            await session.execute(
                text("SELECT set_config('app.tenant_id', :tid, true)"),
                {"tid": str(tenant_id)},
            )
        else:
            await session.execute(text("SELECT set_config('app.tenant_id', '', true)"))
        yield session


async def set_tenant(session: AsyncSession, tenant_id: UUID | None) -> None:
    if tenant_id is None:
        await session.execute(text("SELECT set_config('app.tenant_id', '', true)"))
    else:
        await session.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"),
            {"tid": str(tenant_id)},
        )


async def ping_db() -> dict[str, Any]:
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1 AS ok"))
        row = result.one()
        return {"ok": bool(row.ok)}
