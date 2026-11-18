"""Dashboard read APIs for Phase 5."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from amakuru.core.db import get_db, set_tenant
from amakuru.core.settings import Settings, get_settings
from amakuru.modules.channels.models import (
    ChannelConfig,
    Conversation,
    Feedback,
    Message,
    UnansweredItem,
)
from amakuru.modules.evaluation.harness import format_report, run_eval
from amakuru.modules.evaluation.models import EvalRun
from amakuru.modules.identity.models import User
from amakuru.modules.identity.schemas import UserOut
from amakuru.modules.knowledge.deps import tenant_auth
from amakuru.modules.knowledge.models import (
    STATUS_IN_REVIEW,
    STATUS_PUBLISHED,
    AnswerEntry,
    AnswerVersion,
    Office,
)
from amakuru.modules.knowledge.schemas import VersionOut
from amakuru.modules.platform.models import AuditLog
from amakuru.modules.retrieval.indexing import index_tenant
from amakuru.modules.retrieval.models import QueryTrace
from amakuru.modules.retrieval.providers.embeddings import build_embedding_provider
from amakuru.modules.retrieval.vector_store import PgVectorStore

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["analytics"])

TenantCtx = tuple[User, UserOut, UUID, UUID]


class OverviewOut(BaseModel):
    answered_share: float
    unanswered_open: int
    expiring_soon: int
    published_entries: int
    conversations_7d: int
    feedback_up: int
    feedback_down: int
    language_mix: dict[str, int]
    channel_mix: dict[str, int]
    top_questions: list[dict[str, Any]]


class ConversationOut(BaseModel):
    id: UUID
    channel: str
    language: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    last_preview: str | None = None


class MessageOut(BaseModel):
    id: UUID
    role: str
    content: str
    language: str | None
    trace_id: UUID | None
    meta: dict[str, Any]
    created_at: datetime


class ConversationDetailOut(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]


class TraceOut(BaseModel):
    id: UUID
    question: str
    language: str
    decision: str
    entry_id: UUID | None
    version_id: UUID | None
    steps: list[Any]
    candidates: list[Any]
    latency_ms: int
    tokens: int
    estimated_cost_usd: float
    cache_hit: bool
    created_at: datetime


class UnansweredOut(BaseModel):
    id: UUID
    question: str
    language: str
    channel: str
    office_id: UUID | None
    count: int
    status: str
    created_at: datetime
    updated_at: datetime


class EvalRunOut(BaseModel):
    id: UUID
    trigger: str
    metrics: dict[str, Any]
    thresholds: dict[str, Any]
    passed: bool
    created_at: datetime


class AuditOut(BaseModel):
    id: UUID
    action: str
    resource_type: str
    resource_id: str | None
    actor_user_id: UUID | None
    detail: dict[str, Any]
    created_at: datetime


class ChannelConfigOut(BaseModel):
    widget_key_prefix: str
    allowed_origins: list[Any]
    whatsapp_enabled: bool
    whatsapp_phone_number_id: str | None
    quick_topics: list[Any]
    welcome_message: str


class TeamMemberOut(BaseModel):
    user_id: UUID
    email: str
    full_name: str
    role: str
    office_id: UUID | None


@router.get("/overview", response_model=OverviewOut)
async def overview(
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
) -> OverviewOut:
    _u, _uo, _sid, tenant_id = ctx
    await set_tenant(session, tenant_id)
    since = datetime.now(UTC) - timedelta(days=7)
    soon = (datetime.now(UTC).date()) + timedelta(days=30)

    traces = (
        await session.execute(
            select(QueryTrace.decision, func.count())
            .where(QueryTrace.tenant_id == tenant_id, QueryTrace.created_at >= since)
            .group_by(QueryTrace.decision)
        )
    ).all()
    decision_counts = {str(d): int(c) for d, c in traces}
    total = sum(decision_counts.values()) or 0
    answered = sum(
        decision_counts.get(k, 0) for k in ("verbatim", "compose", "greeting", "clarify")
    )
    unanswered = (
        await session.execute(
            select(func.count())
            .select_from(UnansweredItem)
            .where(UnansweredItem.tenant_id == tenant_id, UnansweredItem.status == "open")
        )
    ).scalar_one()
    expiring = (
        await session.execute(
            select(func.count())
            .select_from(AnswerVersion)
            .where(
                AnswerVersion.tenant_id == tenant_id,
                AnswerVersion.status == STATUS_PUBLISHED,
                AnswerVersion.valid_until.is_not(None),
                AnswerVersion.valid_until <= soon,
            )
        )
    ).scalar_one()
    published = (
        await session.execute(
            select(func.count())
            .select_from(AnswerEntry)
            .join(AnswerVersion, AnswerVersion.entry_id == AnswerEntry.id)
            .where(
                AnswerEntry.tenant_id == tenant_id,
                AnswerEntry.deleted_at.is_(None),
                AnswerVersion.status == STATUS_PUBLISHED,
            )
        )
    ).scalar_one()
    convs = (
        await session.execute(
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.tenant_id == tenant_id, Conversation.created_at >= since)
        )
    ).scalar_one()
    fb = (
        await session.execute(
            select(Feedback.rating, func.count())
            .where(Feedback.tenant_id == tenant_id, Feedback.created_at >= since)
            .group_by(Feedback.rating)
        )
    ).all()
    fb_map = {int(r): int(c) for r, c in fb}
    lang_rows = (
        await session.execute(
            select(QueryTrace.language, func.count())
            .where(QueryTrace.tenant_id == tenant_id, QueryTrace.created_at >= since)
            .group_by(QueryTrace.language)
        )
    ).all()
    channel_rows = (
        await session.execute(
            select(Conversation.channel, func.count())
            .where(Conversation.tenant_id == tenant_id, Conversation.created_at >= since)
            .group_by(Conversation.channel)
        )
    ).all()
    top = (
        await session.execute(
            select(QueryTrace.question, func.count().label("n"))
            .where(QueryTrace.tenant_id == tenant_id, QueryTrace.created_at >= since)
            .group_by(QueryTrace.question)
            .order_by(func.count().desc())
            .limit(8)
        )
    ).all()
    return OverviewOut(
        answered_share=(answered / total) if total else 0.0,
        unanswered_open=int(unanswered or 0),
        expiring_soon=int(expiring or 0),
        published_entries=int(published or 0),
        conversations_7d=int(convs or 0),
        feedback_up=fb_map.get(1, 0),
        feedback_down=fb_map.get(-1, 0),
        language_mix={str(k): int(v) for k, v in lang_rows},
        channel_mix={str(k): int(v) for k, v in channel_rows},
        top_questions=[{"question": q, "count": int(n)} for q, n in top],
    )


@router.get("/review-queue", response_model=list[VersionOut])
async def review_queue(
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
) -> list[VersionOut]:
    _u, _uo, _sid, tenant_id = ctx
    await set_tenant(session, tenant_id)
    rows = (
        (
            await session.execute(
                select(AnswerVersion)
                .where(
                    AnswerVersion.tenant_id == tenant_id,
                    AnswerVersion.status == STATUS_IN_REVIEW,
                )
                .order_by(AnswerVersion.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return [VersionOut.model_validate(r, from_attributes=True) for r in rows]


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
    limit: Annotated[int, Query(ge=1, le=100)] = 40,
) -> list[ConversationOut]:
    _u, _uo, _sid, tenant_id = ctx
    await set_tenant(session, tenant_id)
    rows = (
        (
            await session.execute(
                select(Conversation)
                .where(Conversation.tenant_id == tenant_id)
                .order_by(Conversation.updated_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    out: list[ConversationOut] = []
    for c in rows:
        count = (
            await session.execute(
                select(func.count()).select_from(Message).where(Message.conversation_id == c.id)
            )
        ).scalar_one()
        last = (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == c.id)
                .order_by(Message.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        out.append(
            ConversationOut(
                id=c.id,
                channel=c.channel,
                language=c.language,
                created_at=c.created_at,
                updated_at=c.updated_at,
                message_count=int(count or 0),
                last_preview=(last.content[:120] if last else None),
            )
        )
    return out


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
async def conversation_detail(
    conversation_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
) -> ConversationDetailOut:
    _u, _uo, _sid, tenant_id = ctx
    await set_tenant(session, tenant_id)
    conv = (
        await session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id, Conversation.tenant_id == tenant_id
            )
        )
    ).scalar_one()
    msgs = (
        (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    count = len(msgs)
    return ConversationDetailOut(
        conversation=ConversationOut(
            id=conv.id,
            channel=conv.channel,
            language=conv.language,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            message_count=count,
            last_preview=msgs[-1].content[:120] if msgs else None,
        ),
        messages=[
            MessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                language=m.language,
                trace_id=m.trace_id,
                meta=m.meta or {},
                created_at=m.created_at,
            )
            for m in msgs
        ],
    )


@router.get("/traces/{trace_id}", response_model=TraceOut)
async def get_trace(
    trace_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
) -> TraceOut:
    _u, _uo, _sid, tenant_id = ctx
    await set_tenant(session, tenant_id)
    row = (
        await session.execute(
            select(QueryTrace).where(QueryTrace.id == trace_id, QueryTrace.tenant_id == tenant_id)
        )
    ).scalar_one()
    return TraceOut(
        id=row.id,
        question=row.question,
        language=row.language,
        decision=row.decision,
        entry_id=row.entry_id,
        version_id=row.version_id,
        steps=list(row.steps or []),
        candidates=list(row.candidates or []),
        latency_ms=row.latency_ms,
        tokens=row.tokens,
        estimated_cost_usd=float(row.estimated_cost_usd or 0),
        cache_hit=row.cache_hit,
        created_at=row.created_at,
    )


@router.get("/unanswered", response_model=list[UnansweredOut])
async def unanswered(
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
) -> list[UnansweredOut]:
    _u, _uo, _sid, tenant_id = ctx
    await set_tenant(session, tenant_id)
    rows = (
        (
            await session.execute(
                select(UnansweredItem)
                .where(UnansweredItem.tenant_id == tenant_id, UnansweredItem.status == "open")
                .order_by(UnansweredItem.count.desc(), UnansweredItem.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [UnansweredOut.model_validate(r, from_attributes=True) for r in rows]


@router.get("/eval-runs", response_model=list[EvalRunOut])
async def eval_runs(
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
) -> list[EvalRunOut]:
    _u, _uo, _sid, tenant_id = ctx
    await set_tenant(session, tenant_id)
    rows = (
        (
            await session.execute(
                select(EvalRun)
                .where(EvalRun.tenant_id == tenant_id)
                .order_by(EvalRun.created_at.desc())
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    return [EvalRunOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/eval-runs")
async def trigger_eval(
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    _u, _uo, _sid, tenant_id = ctx
    await set_tenant(session, tenant_id)
    embedder = build_embedding_provider(settings)
    store = PgVectorStore()
    await index_tenant(
        session, tenant_id=tenant_id, embedder=embedder, store=store, settings=settings
    )
    payload = await run_eval(session, tenant_id=tenant_id, settings=settings, trigger="dashboard")
    await session.commit()
    return {"report": format_report(payload), **payload}


@router.get("/audit-log", response_model=list[AuditOut])
async def audit_log(
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[AuditOut]:
    _u, _uo, _sid, tenant_id = ctx
    await set_tenant(session, tenant_id)
    rows = (
        (
            await session.execute(
                select(AuditLog)
                .where(AuditLog.tenant_id == tenant_id)
                .order_by(AuditLog.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        AuditOut(
            id=r.id,
            action=r.action,
            resource_type=r.resource_type,
            resource_id=r.resource_id,
            actor_user_id=r.actor_user_id,
            detail=r.detail or {},
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/channel-config", response_model=ChannelConfigOut)
async def channel_config(
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
) -> ChannelConfigOut:
    _u, _uo, _sid, tenant_id = ctx
    await set_tenant(session, tenant_id)
    row = (
        await session.execute(select(ChannelConfig).where(ChannelConfig.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if row is None:
        return ChannelConfigOut(
            widget_key_prefix="",
            allowed_origins=[],
            whatsapp_enabled=False,
            whatsapp_phone_number_id=None,
            quick_topics=[],
            welcome_message="",
        )
    return ChannelConfigOut(
        widget_key_prefix=row.widget_key_prefix,
        allowed_origins=list(row.allowed_origins or []),
        whatsapp_enabled=row.whatsapp_enabled,
        whatsapp_phone_number_id=row.whatsapp_phone_number_id,
        quick_topics=list(row.quick_topics or []),
        welcome_message=row.welcome_message,
    )


@router.get("/team", response_model=list[TeamMemberOut])
async def team(
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
) -> list[TeamMemberOut]:
    from amakuru.modules.identity.models import Membership

    _u, _uo, _sid, tenant_id = ctx
    await set_tenant(session, tenant_id)
    rows = (
        await session.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.tenant_id == tenant_id)
            .order_by(User.email.asc())
        )
    ).all()
    return [
        TeamMemberOut(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=m.role,
            office_id=m.office_id,
        )
        for m, user in rows
    ]


@router.get("/offices-summary")
async def offices_summary(
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
) -> list[dict[str, Any]]:
    _u, _uo, _sid, tenant_id = ctx
    await set_tenant(session, tenant_id)
    rows = (
        (
            await session.execute(
                select(Office).where(Office.tenant_id == tenant_id, Office.deleted_at.is_(None))
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": str(o.id),
            "name": o.name,
            "contact_person": o.contact_person,
            "phone": o.phone,
            "email": o.email,
            "opening_hours": o.opening_hours,
        }
        for o in rows
    ]
