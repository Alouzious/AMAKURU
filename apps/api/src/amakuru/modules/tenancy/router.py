"""Tenant listing routes (platform admin / member scoped)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from amakuru.core.db import get_db, set_tenant
from amakuru.core.errors import ForbiddenError, NotFoundError
from amakuru.modules.identity.deps import CurrentAuth, get_current_user
from amakuru.modules.identity.schemas import TenantOut
from amakuru.modules.tenancy.models import Tenant

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.get("", response_model=list[TenantOut])
async def list_tenants(
    session: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[CurrentAuth, Depends(get_current_user)],
) -> list[TenantOut]:
    user, user_out, _ = auth
    if user.is_platform_admin:
        result = await session.execute(
            select(Tenant).where(Tenant.deleted_at.is_(None)).order_by(Tenant.name)
        )
        tenants = result.scalars().all()
    else:
        tenant_ids = [m.tenant_id for m in user_out.memberships]
        if not tenant_ids:
            return []
        result = await session.execute(
            select(Tenant).where(Tenant.id.in_(tenant_ids), Tenant.deleted_at.is_(None))
        )
        tenants = result.scalars().all()
    return [
        TenantOut(
            id=t.id,
            name=t.name,
            slug=t.slug,
            plan=t.plan,
            status=t.status,
            residency_mode=t.residency_mode,
            default_language=t.default_language,
            is_demo=t.is_demo,
            demo_label=t.demo_label,
            branding=t.branding or {},
            created_at=t.created_at,
        )
        for t in tenants
    ]


@router.get("/{tenant_id}", response_model=TenantOut)
async def get_tenant(
    tenant_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[CurrentAuth, Depends(get_current_user)],
) -> TenantOut:
    user, user_out, _ = auth
    allowed = user.is_platform_admin or any(m.tenant_id == tenant_id for m in user_out.memberships)
    if not allowed:
        raise ForbiddenError("No access to this tenant")

    await set_tenant(session, tenant_id)
    result = await session.execute(
        select(Tenant).where(Tenant.id == tenant_id, Tenant.deleted_at.is_(None))
    )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise NotFoundError("Tenant not found")
    return TenantOut(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        plan=tenant.plan,
        status=tenant.status,
        residency_mode=tenant.residency_mode,
        default_language=tenant.default_language,
        is_demo=tenant.is_demo,
        demo_label=tenant.demo_label,
        branding=tenant.branding or {},
        created_at=tenant.created_at,
    )
