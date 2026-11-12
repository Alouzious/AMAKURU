"""Retrieval HTTP routes."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from amakuru.core.db import get_db
from amakuru.core.errors import ForbiddenError
from amakuru.core.settings import Settings, get_settings
from amakuru.modules.generation.cache import ReplyCache
from amakuru.modules.identity.models import User
from amakuru.modules.identity.schemas import UserOut
from amakuru.modules.knowledge.deps import can_admin_tenant, load_memberships, tenant_auth
from amakuru.modules.platform.audit import write_audit
from amakuru.modules.retrieval.indexing import index_tenant
from amakuru.modules.retrieval.providers.embeddings import build_embedding_provider
from amakuru.modules.retrieval.providers.reranker import build_reranker
from amakuru.modules.retrieval.service import retrieve
from amakuru.modules.retrieval.vector_store import PgVectorStore

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["retrieval"])

TenantCtx = tuple[User, UserOut, UUID, UUID]


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    language: str = "en"


class AskResponse(BaseModel):
    trace_id: str
    decision: str
    reason: str
    score: float
    entry_id: str | None
    version_id: str | None
    reply: str | None
    candidates: list[dict[str, Any]]
    latency_ms: int
    cache_hit: bool = False
    machine_translated: bool = False
    tokens: int = 0
    estimated_cost_usd: float = 0.0


class IndexResponse(BaseModel):
    indexed: int
    versions: int
    variants: int
    model_id: str


@router.post("/ask", response_model=AskResponse)
async def ask(
    body: AskRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AskResponse:
    _user, _uo, _sid, tenant_id = ctx
    embedder = build_embedding_provider(settings)
    reranker = build_reranker(settings)
    store = PgVectorStore()
    result = await retrieve(
        session,
        tenant_id=tenant_id,
        question=body.question,
        language=body.language,
        settings=settings,
        embedder=embedder,
        reranker=reranker,
        store=store,
    )
    await session.commit()
    return AskResponse(**result)


@router.post("/index", response_model=IndexResponse)
async def reindex(
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[TenantCtx, Depends(tenant_auth)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> IndexResponse:
    user, _uo, _sid, tenant_id = ctx
    memberships = await load_memberships(session, tenant_id=tenant_id, user_id=user.id)
    if not can_admin_tenant(memberships, is_platform_admin=user.is_platform_admin):
        raise ForbiddenError("Tenant admin required to reindex")
    embedder = build_embedding_provider(settings)
    store = PgVectorStore()
    stats = await index_tenant(
        session,
        tenant_id=tenant_id,
        embedder=embedder,
        store=store,
        settings=settings,
    )
    await ReplyCache(settings).bump_knowledge_epoch(tenant_id)
    await write_audit(
        session,
        action="retrieval.reindex",
        resource_type="tenant",
        resource_id=str(tenant_id),
        tenant_id=tenant_id,
        actor_user_id=user.id,
        detail=stats,
    )
    await session.commit()
    return IndexResponse(**stats)
