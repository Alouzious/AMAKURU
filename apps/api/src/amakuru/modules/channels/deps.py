"""Widget / channel authentication helpers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from amakuru.core.db import get_db, set_tenant
from amakuru.core.errors import AuthError, ForbiddenError
from amakuru.modules.channels.keys import verify_widget_key
from amakuru.modules.channels.models import ChannelConfig
from amakuru.modules.tenancy.models import Tenant


async def resolve_widget_tenant(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    x_amakuru_key: Annotated[str | None, Header(alias="X-Amakuru-Key")] = None,
) -> tuple[Tenant, ChannelConfig]:
    if not x_amakuru_key:
        raise AuthError("Missing X-Amakuru-Key")
    # Superuser connection: look up by hash without tenant yet
    await set_tenant(session, None)
    # Compare by scanning prefixes then verifying hash (demo scale is fine)
    prefix = x_amakuru_key[:12]
    result = await session.execute(
        select(ChannelConfig).where(ChannelConfig.widget_key_prefix == prefix)
    )
    configs = list(result.scalars().all())
    config: ChannelConfig | None = None
    for row in configs:
        if verify_widget_key(x_amakuru_key, row.widget_key_hash):
            config = row
            break
    if config is None:
        raise AuthError("Invalid widget key")

    origin = request.headers.get("origin") or request.headers.get("referer")
    allowed = list(config.allowed_origins or [])
    if allowed and origin:
        ok = any(origin.startswith(a) or a == "*" for a in allowed)
        if not ok:
            raise ForbiddenError("Origin not allowed for this widget")

    tenant = (
        await session.execute(select(Tenant).where(Tenant.id == config.tenant_id))
    ).scalar_one()
    if tenant.status != "active" or tenant.deleted_at is not None:
        raise ForbiddenError("Tenant inactive")
    await set_tenant(session, tenant.id)
    return tenant, config
