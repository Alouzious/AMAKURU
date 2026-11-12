"""Billing, API keys, branding, onboarding, external ask."""

from __future__ import annotations

import csv
import io
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from amakuru.core.db import get_db, set_tenant
from amakuru.core.errors import AuthError, ForbiddenError, NotFoundError
from amakuru.core.settings import Settings, get_settings
from amakuru.modules.billing.catalog import PLAN_CATALOG, plan_summary
from amakuru.modules.billing.entitlements import (
    assert_conversation_quota,
    require_api_access,
    require_white_label,
    usage_snapshot,
)
from amakuru.modules.billing.keys import (
    api_key_prefix,
    generate_api_key,
    hash_api_key,
    verify_api_key,
)
from amakuru.modules.billing.metering import list_usage
from amakuru.modules.billing.models import ApiKey, Plan
from amakuru.modules.billing.onboarding import onboard_tenant
from amakuru.modules.billing.schemas import (
    ApiKeyCreate,
    ApiKeyCreatedOut,
    ApiKeyOut,
    BillingSummaryOut,
    BrandingPatch,
    ExternalAskIn,
    ExternalAskOut,
    OnboardRequest,
    OnboardResult,
    PlanOut,
    UsageRowOut,
)
from amakuru.modules.channels.service import run_chat_turn
from amakuru.modules.identity.deps import CurrentAuth, require_csrf
from amakuru.modules.identity.models import User
from amakuru.modules.identity.schemas import UserOut
from amakuru.modules.knowledge.deps import can_admin_tenant, load_memberships, tenant_auth
from amakuru.modules.platform.audit import write_audit
from amakuru.modules.tenancy.models import Tenant

router = APIRouter(tags=["billing"])
external_router = APIRouter(prefix="/external", tags=["external"])

TenantCtx = tuple[User, UserOut, UUID, UUID]


def _plan_out(code: str) -> PlanOut:
    s = plan_summary(code)
    return PlanOut(
        code=s["code"], name=s["name"], description=s["description"], entitlements=s["entitlements"]
    )


@router.get("/plans", response_model=list[PlanOut])
async def list_plans() -> list[PlanOut]:
    return [_plan_out(code) for code in PLAN_CATALOG]


@router.post("/onboarding", response_model=OnboardResult)
async def create_tenant_onboarding(
    body: OnboardRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[CurrentAuth, Depends(require_csrf)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> OnboardResult:
    user, _, _ = auth
    if not user.is_platform_admin:
        raise ForbiddenError("Only platform administrators can onboard tenants")
    result = await onboard_tenant(session, body=body, actor_user_id=user.id, settings=settings)
    await session.commit()
    return result


@router.get("/tenants/{tenant_id}/billing", response_model=BillingSummaryOut)
async def get_billing(
    tenant_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
) -> BillingSummaryOut:
    _user, _uo, _sid, tid = ctx
    snap = await usage_snapshot(session, tid)
    tenant = (await session.execute(select(Tenant).where(Tenant.id == tid))).scalar_one()
    return BillingSummaryOut(
        plan=snap["plan"],
        plan_detail=_plan_out(snap["plan"]),
        entitlements=snap["entitlements"],
        usage=snap["usage"],
        residency_mode=tenant.residency_mode,
        branding=tenant.branding or {},
    )


@router.get("/tenants/{tenant_id}/usage", response_model=list[UsageRowOut])
async def get_usage(
    tenant_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
    from_day: Annotated[date | None, Query(alias="from")] = None,
    to_day: Annotated[date | None, Query(alias="to")] = None,
) -> list[UsageRowOut]:
    _u, _uo, _sid, tid = ctx
    end = to_day or datetime.now(UTC).date()
    start = from_day or (end - timedelta(days=30))
    rows = await list_usage(session, tenant_id=tid, from_day=start, to_day=end)
    return [
        UsageRowOut(
            day=r.day,
            event_type=r.event_type,
            quantity=r.quantity,
            estimated_cost_usd=r.estimated_cost_usd,
        )
        for r in rows
    ]


@router.get("/tenants/{tenant_id}/usage/export")
async def export_usage(
    tenant_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
    from_day: Annotated[date | None, Query(alias="from")] = None,
    to_day: Annotated[date | None, Query(alias="to")] = None,
) -> Response:
    _u, _uo, _sid, tid = ctx
    end = to_day or datetime.now(UTC).date()
    start = from_day or (end - timedelta(days=30))
    rows = await list_usage(session, tenant_id=tid, from_day=start, to_day=end)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["day", "event_type", "quantity", "estimated_cost_usd"])
    for r in rows:
        writer.writerow([r.day.isoformat(), r.event_type, r.quantity, str(r.estimated_cost_usd)])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="amakuru-usage-{tid}.csv"',
        },
    )


@router.patch("/tenants/{tenant_id}/branding")
async def patch_branding(
    tenant_id: UUID,
    body: BrandingPatch,
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
) -> dict[str, Any]:
    user, _uo, _sid, tid = ctx
    memberships = await load_memberships(session, tenant_id=tid, user_id=user.id)
    if not can_admin_tenant(memberships, is_platform_admin=user.is_platform_admin):
        raise ForbiddenError("Tenant admin required")

    tenant = (await session.execute(select(Tenant).where(Tenant.id == tid))).scalar_one()
    patch = body.model_dump(exclude_none=True)
    needs_wl = any(k in patch for k in ("logo_url", "surface", "heading_font", "custom_domain"))
    if needs_wl:
        await require_white_label(session, tid)
    branding = dict(tenant.branding or {})
    branding.update(patch)
    tenant.branding = branding
    await write_audit(
        session,
        action="branding.updated",
        resource_type="tenant",
        resource_id=str(tid),
        tenant_id=tid,
        actor_user_id=user.id,
        detail={"keys": list(patch.keys())},
    )
    await session.commit()
    return {"branding": branding}


@router.get("/tenants/{tenant_id}/api-keys", response_model=list[ApiKeyOut])
async def list_api_keys(
    tenant_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
) -> list[ApiKeyOut]:
    _u, _uo, _sid, tid = ctx
    result = await session.execute(
        select(ApiKey).where(ApiKey.tenant_id == tid).order_by(ApiKey.created_at.desc())
    )
    return [
        ApiKeyOut(
            id=k.id,
            name=k.name,
            key_prefix=k.key_prefix,
            scopes=list(k.scopes or []),
            created_at=k.created_at,
            last_used_at=k.last_used_at,
            revoked_at=k.revoked_at,
        )
        for k in result.scalars().all()
    ]


@router.post("/tenants/{tenant_id}/api-keys", response_model=ApiKeyCreatedOut)
async def create_api_key(
    tenant_id: UUID,
    body: ApiKeyCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
) -> ApiKeyCreatedOut:
    user, _uo, _sid, tid = ctx
    memberships = await load_memberships(session, tenant_id=tid, user_id=user.id)
    if not can_admin_tenant(memberships, is_platform_admin=user.is_platform_admin):
        raise ForbiddenError("Tenant admin required")
    await require_api_access(session, tid)

    raw = generate_api_key()
    row = ApiKey(
        id=uuid4(),
        tenant_id=tid,
        name=body.name,
        key_hash=hash_api_key(raw),
        key_prefix=api_key_prefix(raw),
        scopes=body.scopes or ["ask"],
        created_by=user.id,
    )
    session.add(row)
    await write_audit(
        session,
        action="api_key.created",
        resource_type="api_key",
        resource_id=str(row.id),
        tenant_id=tid,
        actor_user_id=user.id,
        detail={"name": body.name, "prefix": row.key_prefix},
    )
    await session.commit()
    return ApiKeyCreatedOut(
        id=row.id,
        name=row.name,
        key_prefix=row.key_prefix,
        scopes=list(row.scopes or []),
        created_at=row.created_at,
        last_used_at=None,
        revoked_at=None,
        raw_key=raw,
    )


@router.delete("/tenants/{tenant_id}/api-keys/{key_id}", response_model=ApiKeyOut)
async def revoke_api_key(
    tenant_id: UUID,
    key_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
) -> ApiKeyOut:
    user, _uo, _sid, tid = ctx
    memberships = await load_memberships(session, tenant_id=tid, user_id=user.id)
    if not can_admin_tenant(memberships, is_platform_admin=user.is_platform_admin):
        raise ForbiddenError("Tenant admin required")
    result = await session.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.tenant_id == tid)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise NotFoundError("API key not found")
    row.revoked_at = datetime.now(UTC)
    await write_audit(
        session,
        action="api_key.revoked",
        resource_type="api_key",
        resource_id=str(row.id),
        tenant_id=tid,
        actor_user_id=user.id,
        detail={},
    )
    await session.commit()
    return ApiKeyOut(
        id=row.id,
        name=row.name,
        key_prefix=row.key_prefix,
        scopes=list(row.scopes or []),
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
    )


async def resolve_api_key_tenant(
    session: AsyncSession,
    authorization: str | None,
) -> tuple[UUID, ApiKey]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("Bearer API key required")
    raw = authorization.split(" ", 1)[1].strip()
    if not raw.startswith("ak_api_"):
        raise AuthError("Invalid API key")
    digest = hash_api_key(raw)
    # Lookup without tenant RLS — keys are unique globally by hash
    result = await session.execute(select(ApiKey).where(ApiKey.key_hash == digest))
    row = result.scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        raise AuthError("Invalid or revoked API key")
    if not verify_api_key(raw, row.key_hash):
        raise AuthError("Invalid API key")
    await set_tenant(session, row.tenant_id)
    row.last_used_at = datetime.now(UTC)
    await session.flush()
    return row.tenant_id, row


@external_router.post("/ask", response_model=ExternalAskOut)
async def external_ask(
    body: ExternalAskIn,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> ExternalAskOut:
    tenant_id, key = await resolve_api_key_tenant(session, authorization)
    if "ask" not in (key.scopes or []):
        raise ForbiddenError("API key lacks ask scope")
    await require_api_access(session, tenant_id)
    await assert_conversation_quota(session, tenant_id)
    result = await run_chat_turn(
        session,
        tenant_id=tenant_id,
        question=body.question,
        language=body.language,
        channel="api",
        settings=settings,
    )
    await session.commit()
    return ExternalAskOut(
        reply=result.get("reply") or "",
        decision=result.get("decision") or "handoff",
        trace_id=result.get("trace_id") or "",
        source=result.get("source"),
        handoff=result.get("handoff"),
        estimated_cost_usd=float(result.get("estimated_cost_usd") or 0),
    )


async def ensure_plans_seeded(session: AsyncSession) -> None:
    for code, meta in PLAN_CATALOG.items():
        existing = await session.execute(select(Plan).where(Plan.code == code))
        if existing.scalar_one_or_none() is None:
            session.add(
                Plan(
                    code=code,
                    name=meta["name"],
                    description=meta["description"],
                    entitlements=meta["entitlements"],
                    is_active=True,
                )
            )
    await session.flush()
