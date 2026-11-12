"""Authentication and membership service."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from amakuru.core.errors import AuthError, ForbiddenError
from amakuru.core.security import (
    csrf_token,
    hash_password,
    new_token,
    refresh_expiry,
    session_expiry,
    verify_password,
)
from amakuru.core.settings import Settings
from amakuru.modules.identity.models import Membership, Session, User
from amakuru.modules.identity.schemas import MembershipOut, UserOut
from amakuru.modules.platform.audit import write_audit
from amakuru.modules.tenancy.models import Tenant


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: UUID) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str,
    is_platform_admin: bool = False,
) -> User:
    user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        full_name=full_name,
        is_platform_admin=is_platform_admin,
    )
    session.add(user)
    await session.flush()
    return user


async def list_memberships(session: AsyncSession, user_id: UUID) -> list[MembershipOut]:
    result = await session.execute(
        select(Membership, Tenant)
        .join(Tenant, Tenant.id == Membership.tenant_id)
        .where(Membership.user_id == user_id, Tenant.deleted_at.is_(None))
    )
    rows = result.all()
    return [
        MembershipOut(
            tenant_id=tenant.id,
            tenant_name=tenant.name,
            tenant_slug=tenant.slug,
            role=membership.role,
            office_id=membership.office_id,
            is_demo=tenant.is_demo,
        )
        for membership, tenant in rows
    ]


async def build_user_out(session: AsyncSession, user: User, *, csrf: str | None = None) -> UserOut:
    memberships = await list_memberships(session, user.id)
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_platform_admin=user.is_platform_admin,
        totp_enabled=user.totp_enabled,
        memberships=memberships,
        csrf_token=csrf,
    )


async def login(
    session: AsyncSession,
    settings: Settings,
    *,
    email: str,
    password: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[UserOut, str, str]:
    user = await get_user_by_email(session, email)
    if user is None or not user.is_active or user.deleted_at is not None:
        raise AuthError("Invalid email or password")
    if not verify_password(user.password_hash, password):
        raise AuthError("Invalid email or password")

    refresh = new_token(48)
    csrf = csrf_token()
    sess = Session(
        user_id=user.id,
        refresh_token_hash=_hash_token(refresh),
        csrf_token=csrf,
        expires_at=session_expiry(settings),
        refresh_expires_at=refresh_expiry(settings),
    )
    session.add(sess)
    await session.flush()

    await write_audit(
        session,
        action="auth.login",
        resource_type="user",
        resource_id=str(user.id),
        actor_user_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    user_out = await build_user_out(session, user, csrf=csrf)
    return user_out, str(sess.id), refresh


async def logout(
    session: AsyncSession,
    *,
    session_id: UUID,
    user_id: UUID,
) -> None:
    result = await session.execute(select(Session).where(Session.id == session_id))
    sess = result.scalar_one_or_none()
    if sess is None:
        return
    sess.revoked_at = datetime.now(UTC)
    await write_audit(
        session,
        action="auth.logout",
        resource_type="session",
        resource_id=str(session_id),
        actor_user_id=user_id,
    )


async def get_valid_session(session: AsyncSession, session_id: UUID) -> Session | None:
    result = await session.execute(select(Session).where(Session.id == session_id))
    sess = result.scalar_one_or_none()
    if sess is None or sess.revoked_at is not None:
        return None
    now = datetime.now(UTC)
    if sess.expires_at < now and sess.refresh_expires_at < now:
        return None
    return sess


async def refresh_session(
    session: AsyncSession,
    settings: Settings,
    *,
    session_id: UUID,
    refresh_token: str,
) -> tuple[UserOut, str, str]:
    result = await session.execute(select(Session).where(Session.id == session_id))
    sess = result.scalar_one_or_none()
    if (
        sess is None
        or sess.revoked_at is not None
        or sess.refresh_expires_at < datetime.now(UTC)
        or sess.refresh_token_hash != _hash_token(refresh_token)
    ):
        raise AuthError("Session expired")

    user = await get_user_by_id(session, sess.user_id)
    if user is None or not user.is_active:
        raise AuthError("Session expired")

    new_refresh = new_token(48)
    sess.refresh_token_hash = _hash_token(new_refresh)
    sess.csrf_token = csrf_token()
    sess.expires_at = session_expiry(settings)
    sess.refresh_expires_at = refresh_expiry(settings)
    await session.flush()

    user_out = await build_user_out(session, user, csrf=sess.csrf_token)
    return user_out, str(sess.id), new_refresh


def require_platform_admin(user: User) -> None:
    if not user.is_platform_admin:
        raise ForbiddenError("Platform admin required")


def require_tenant_role(memberships: list[MembershipOut], tenant_id: UUID, roles: set[str]) -> None:
    for m in memberships:
        if m.tenant_id == tenant_id and m.role in roles:
            return
    raise ForbiddenError("Insufficient tenant role")
