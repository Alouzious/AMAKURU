"""Knowledge HTTP routes."""

from __future__ import annotations

import json
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from amakuru.core.db import get_db
from amakuru.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from amakuru.core.security import encrypt_secret
from amakuru.core.settings import Settings, get_settings
from amakuru.modules.identity.models import User
from amakuru.modules.identity.schemas import UserOut
from amakuru.modules.knowledge import service as knowledge_service
from amakuru.modules.knowledge.deps import can_admin_tenant, load_memberships, tenant_auth
from amakuru.modules.knowledge.importing import preview_import, run_import
from amakuru.modules.knowledge.models import Connector, SearchEvent
from amakuru.modules.knowledge.schemas import (
    ConnectorCreate,
    ConnectorOut,
    SearchEventOut,
    EntryCreate,
    EntryOut,
    ImportPreviewOut,
    ImportRunOut,
    MessageOut,
    NeedsAnswerOut,
    OfficeCreate,
    OfficeOut,
    OfficeUpdate,
    SyncOut,
    VersionCreate,
    VersionOut,
)
from amakuru.modules.platform.audit import write_audit

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["knowledge"])

TenantCtx = tuple[User, UserOut, UUID, UUID]


@router.post("/offices", response_model=OfficeOut)
async def create_office(
    body: OfficeCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
) -> OfficeOut:
    user, _uo, _sid, tenant_id = ctx
    memberships = await load_memberships(session, tenant_id=tenant_id, user_id=user.id)
    if not can_admin_tenant(memberships, is_platform_admin=user.is_platform_admin):
        raise ForbiddenError("Tenant admin required")
    out = await knowledge_service.create_office(session, tenant_id=tenant_id, body=body, actor=user)
    await session.commit()
    return out


@router.get("/offices", response_model=list[OfficeOut])
async def list_offices(
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
) -> list[OfficeOut]:
    _u, _uo, _sid, tenant_id = ctx
    return await knowledge_service.list_offices(session, tenant_id=tenant_id)


@router.patch("/offices/{office_id}", response_model=OfficeOut)
async def update_office(
    office_id: UUID,
    body: OfficeUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
) -> OfficeOut:
    user, _uo, _sid, tenant_id = ctx
    memberships = await load_memberships(session, tenant_id=tenant_id, user_id=user.id)
    if not can_admin_tenant(memberships, is_platform_admin=user.is_platform_admin):
        raise ForbiddenError("Tenant admin required")
    out = await knowledge_service.update_office(
        session, tenant_id=tenant_id, office_id=office_id, body=body, actor=user
    )
    await session.commit()
    return out


@router.post("/answer-entries", response_model=EntryOut)
async def create_entry(
    body: EntryCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
) -> EntryOut:
    user, _uo, _sid, tenant_id = ctx
    out = await knowledge_service.create_entry(session, tenant_id=tenant_id, body=body, actor=user)
    await session.commit()
    return out


@router.get("/answer-entries", response_model=list[EntryOut])
async def list_entries(
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
) -> list[EntryOut]:
    _u, _uo, _sid, tenant_id = ctx
    return await knowledge_service.list_entries(session, tenant_id=tenant_id)


@router.get("/answer-entries/{entry_id}", response_model=EntryOut)
async def get_entry(
    entry_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
) -> EntryOut:
    _u, _uo, _sid, tenant_id = ctx
    return await knowledge_service.get_entry(session, tenant_id=tenant_id, entry_id=entry_id)


@router.post("/answer-entries/{entry_id}/versions", response_model=VersionOut)
async def add_version(
    entry_id: UUID,
    body: VersionCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
) -> VersionOut:
    user, _uo, _sid, tenant_id = ctx
    out = await knowledge_service.add_version(
        session, tenant_id=tenant_id, entry_id=entry_id, body=body, actor=user
    )
    await session.commit()
    return out


@router.get("/answer-entries/{entry_id}/versions", response_model=list[VersionOut])
async def list_versions(
    entry_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
) -> list[VersionOut]:
    _u, _uo, _sid, tenant_id = ctx
    return await knowledge_service.list_versions(session, tenant_id=tenant_id, entry_id=entry_id)


@router.post("/versions/{version_id}/submit", response_model=VersionOut)
async def submit_version(
    version_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
) -> VersionOut:
    user, _uo, _sid, tenant_id = ctx
    out = await knowledge_service.submit_version(
        session, tenant_id=tenant_id, version_id=version_id, actor=user
    )
    await session.commit()
    return out


@router.post("/versions/{version_id}/approve", response_model=VersionOut)
async def approve_version(
    version_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> VersionOut:
    user, _uo, _sid, tenant_id = ctx
    out = await knowledge_service.approve_version(
        session,
        tenant_id=tenant_id,
        version_id=version_id,
        actor=user,
        settings=settings,
    )
    await session.commit()
    return out


@router.post("/versions/{version_id}/publish", response_model=VersionOut)
async def publish_version(
    version_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> VersionOut:
    user, _uo, _sid, tenant_id = ctx
    out = await knowledge_service.publish_version(
        session,
        tenant_id=tenant_id,
        version_id=version_id,
        actor=user,
        settings=settings,
    )
    await session.commit()
    return out


@router.post("/versions/{version_id}/reject", response_model=VersionOut)
async def reject_version(
    version_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> VersionOut:
    user, _uo, _sid, tenant_id = ctx
    out = await knowledge_service.reject_version(
        session,
        tenant_id=tenant_id,
        version_id=version_id,
        actor=user,
        settings=settings,
    )
    await session.commit()
    return out


@router.get("/expiring-soon", response_model=list[VersionOut])
async def expiring_soon(
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
) -> list[VersionOut]:
    _u, _uo, _sid, tenant_id = ctx
    return await knowledge_service.list_expiring_soon(session, tenant_id=tenant_id)


@router.get("/needs-answer", response_model=list[NeedsAnswerOut])
async def needs_answer(
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
) -> list[NeedsAnswerOut]:
    _u, _uo, _sid, tenant_id = ctx
    return await knowledge_service.list_needs_answer(session, tenant_id=tenant_id)


@router.post("/imports/preview", response_model=ImportPreviewOut)
async def imports_preview(
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
    file: Annotated[UploadFile, File()],
) -> ImportPreviewOut:
    _u, _uo, _sid, _tenant_id = ctx
    content = await file.read()
    return preview_import(content, file.filename or "import.csv")


@router.post("/imports/run", response_model=ImportRunOut)
async def imports_run(
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
    file: Annotated[UploadFile, File()],
    mapping_json: Annotated[str, Form()],
    default_office_id: Annotated[str | None, Form()] = None,
) -> ImportRunOut:
    user, _uo, _sid, tenant_id = ctx
    try:
        mapping = json.loads(mapping_json)
    except json.JSONDecodeError as exc:
        raise ValidationAppError("mapping_json must be valid JSON") from exc
    if not isinstance(mapping, dict):
        raise ValidationAppError("mapping_json must be an object")
    office_uuid = UUID(default_office_id) if default_office_id else None
    content = await file.read()
    out = await run_import(
        session,
        tenant_id=tenant_id,
        content=content,
        filename=file.filename or "import.csv",
        mapping={str(k): str(v) for k, v in mapping.items()},
        actor_id=user.id,
        default_office_id=office_uuid,
    )
    await session.commit()
    return out


@router.post("/connectors", response_model=ConnectorOut)
async def create_connector(
    body: ConnectorCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ConnectorOut:
    user, _uo, _sid, tenant_id = ctx
    memberships = await load_memberships(session, tenant_id=tenant_id, user_id=user.id)
    if not can_admin_tenant(memberships, is_platform_admin=user.is_platform_admin):
        raise ForbiddenError("Tenant admin required")
    encrypted = None
    if body.config:
        encrypted = encrypt_secret(settings, json.dumps(body.config))
    connector = Connector(
        id=uuid4(),
        tenant_id=tenant_id,
        name=body.name,
        adapter_type=body.adapter_type,
        config_encrypted=encrypted,
        field_mapping=body.field_mapping,
        schedule_cron=body.schedule_cron,
    )
    session.add(connector)
    await session.flush()
    await write_audit(
        session,
        action="connector.create",
        resource_type="connector",
        resource_id=str(connector.id),
        tenant_id=tenant_id,
        actor_user_id=user.id,
    )
    await session.commit()
    return ConnectorOut(
        id=connector.id,
        name=connector.name,
        adapter_type=connector.adapter_type,
        field_mapping=connector.field_mapping,
        schedule_cron=connector.schedule_cron,
        is_active=connector.is_active,
        last_synced_at=connector.last_synced_at,
        created_at=connector.created_at,
    )


@router.get("/connectors", response_model=list[ConnectorOut])
async def list_connectors(
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
) -> list[ConnectorOut]:
    _u, _uo, _sid, tenant_id = ctx
    result = await session.execute(
        select(Connector).where(Connector.tenant_id == tenant_id).order_by(Connector.name)
    )
    return [
        ConnectorOut(
            id=c.id,
            name=c.name,
            adapter_type=c.adapter_type,
            field_mapping=c.field_mapping,
            schedule_cron=c.schedule_cron,
            is_active=c.is_active,
            last_synced_at=c.last_synced_at,
            created_at=c.created_at,
        )
        for c in result.scalars().all()
    ]


@router.post("/connectors/{connector_id}/sync", response_model=SyncOut)
async def sync_connector_endpoint(
    connector_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
    settings: Annotated[Settings, Depends(get_settings)],
    default_office_id: UUID | None = None,
) -> SyncOut:
    from amakuru.modules.knowledge.sync import sync_connector

    user, _uo, _sid, tenant_id = ctx
    result = await session.execute(
        select(Connector).where(Connector.id == connector_id, Connector.tenant_id == tenant_id)
    )
    connector = result.scalar_one_or_none()
    if connector is None:
        raise NotFoundError("Connector not found")

    stats = await sync_connector(
        session,
        connector=connector,
        settings=settings,
        actor_id=user.id,
        default_office_id=default_office_id,
    )
    await session.commit()
    return SyncOut(
        job_id=stats["job_id"],
        drafts_created=int(stats["drafts_created"]),
        needs_answer=int(stats["needs_answer"]),
    )


@router.get("/search-events", response_model=list[SearchEventOut])
async def list_search_events(
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
    limit: int = 100,
) -> list[SearchEventOut]:
    _u, _uo, _sid, tenant_id = ctx
    result = await session.execute(
        select(SearchEvent)
        .where(SearchEvent.tenant_id == tenant_id)
        .order_by(SearchEvent.count.desc(), SearchEvent.last_asked_at.desc())
        .limit(min(limit, 500))
    )
    return [
        SearchEventOut(
            id=e.id,
            question=e.question,
            language=e.language,
            channel=e.channel,
            decision=e.decision,
            answered=e.answered,
            count=e.count,
            promoted=e.promoted,
            last_asked_at=e.last_asked_at,
            created_at=e.created_at,
        )
        for e in result.scalars().all()
    ]


@router.post("/search-events/promote", response_model=MessageOut)
async def promote_search_events(
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageOut:
    from amakuru.modules.knowledge.search_intel import promote_hot_searches_to_drafts

    user, _uo, _sid, tenant_id = ctx
    memberships = await load_memberships(session, tenant_id=tenant_id, user_id=user.id)
    if not can_admin_tenant(memberships, is_platform_admin=user.is_platform_admin):
        raise ForbiddenError("Tenant admin required")
    out = await promote_hot_searches_to_drafts(
        session,
        tenant_id=tenant_id,
        actor_id=user.id,
        min_count=settings.search_promote_min_count,
    )
    await session.commit()
    return MessageOut(message=f"Promoted {out['created']} hot searches into the needs-answer queue.")
