"""Tenant-scoped knowledge dependencies."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from amakuru.core.db import get_db, set_tenant
from amakuru.core.errors import ForbiddenError
from amakuru.modules.identity.deps import CurrentAuth, require_csrf
from amakuru.modules.identity.models import (
    ROLE_OFFICE_APPROVER,
    ROLE_OFFICE_EDITOR,
    ROLE_TENANT_ADMIN,
    Membership,
    User,
)
from amakuru.modules.identity.schemas import UserOut


async def tenant_auth(
    tenant_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[CurrentAuth, Depends(require_csrf)],
) -> tuple[User, UserOut, UUID, UUID]:
    """Authenticate, authorize tenant access, and set RLS tenant context."""
    user, user_out, session_id = auth
    if not user.is_platform_admin and not any(
        m.tenant_id == tenant_id for m in user_out.memberships
    ):
        raise ForbiddenError("No access to this tenant")
    await set_tenant(session, tenant_id)
    return user, user_out, session_id, tenant_id


async def load_memberships(
    session: AsyncSession, *, tenant_id: UUID, user_id: UUID
) -> list[Membership]:
    result = await session.execute(
        select(Membership).where(Membership.tenant_id == tenant_id, Membership.user_id == user_id)
    )
    return list(result.scalars().all())


def can_edit_office(
    memberships: list[Membership], office_id: UUID, *, is_platform_admin: bool
) -> bool:
    if is_platform_admin:
        return True
    for m in memberships:
        if m.role == ROLE_TENANT_ADMIN:
            return True
        if m.role == ROLE_OFFICE_EDITOR and (m.office_id is None or m.office_id == office_id):
            return True
    return False


def can_approve_office(
    memberships: list[Membership], office_id: UUID, *, is_platform_admin: bool
) -> bool:
    if is_platform_admin:
        return True
    for m in memberships:
        if m.role == ROLE_TENANT_ADMIN:
            return True
        if m.role == ROLE_OFFICE_APPROVER and (m.office_id is None or m.office_id == office_id):
            return True
    return False


def can_admin_tenant(memberships: list[Membership], *, is_platform_admin: bool) -> bool:
    if is_platform_admin:
        return True
    return any(m.role == ROLE_TENANT_ADMIN for m in memberships)
