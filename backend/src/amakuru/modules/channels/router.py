"""Public widget chat API (streaming + bootstrap)."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from amakuru.core.db import get_db
from amakuru.core.settings import Settings, get_settings
from amakuru.modules.channels.deps import resolve_widget_tenant
from amakuru.modules.channels.models import DEFAULT_QUICK_TOPICS, ChannelConfig, Feedback
from amakuru.modules.channels.service import run_chat_turn
from amakuru.modules.tenancy.models import Tenant

router = APIRouter(prefix="/public/chat", tags=["channels-public"])

WidgetCtx = tuple[Tenant, ChannelConfig]


class BootstrapResponse(BaseModel):
    tenant_name: str
    tenant_slug: str
    welcome_message: str
    quick_topics: list[dict[str, Any]]
    default_language: str
    branding: dict[str, Any]
    privacy_notice: str


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    language: str = "en"
    conversation_id: UUID | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    trace_id: str
    decision: str
    reply: str | None
    source: dict[str, Any] | None = None
    handoff: dict[str, Any] | None = None
    score: float = 0.0
    cache_hit: bool = False
    latency_ms: int = 0


class FeedbackRequest(BaseModel):
    trace_id: UUID
    conversation_id: UUID | None = None
    rating: int = Field(ge=-1, le=1)
    reason: str | None = None


PRIVACY = (
    "Please do not type personal details such as phone numbers, national IDs, "
    "or card numbers. Answers come only from approved organization information."
)


@router.get("/bootstrap", response_model=BootstrapResponse)
async def bootstrap(
    ctx: Annotated[WidgetCtx, Depends(resolve_widget_tenant)],
) -> BootstrapResponse:
    tenant, config = ctx
    topics = config.quick_topics or DEFAULT_QUICK_TOPICS
    return BootstrapResponse(
        tenant_name=tenant.name,
        tenant_slug=tenant.slug,
        welcome_message=config.welcome_message,
        quick_topics=list(topics),
        default_language=tenant.default_language,
        branding=tenant.branding or {},
        privacy_notice=PRIVACY,
    )


@router.post("/message", response_model=ChatResponse)
async def chat_message(
    body: ChatRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[WidgetCtx, Depends(resolve_widget_tenant)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ChatResponse:
    tenant, _config = ctx
    result = await run_chat_turn(
        session,
        tenant_id=tenant.id,
        question=body.question,
        language=body.language,
        channel="widget",
        settings=settings,
        conversation_id=body.conversation_id,
    )
    await session.commit()
    return ChatResponse(
        conversation_id=result["conversation_id"],
        trace_id=result["trace_id"],
        decision=result["decision"],
        reply=result.get("reply"),
        source=result.get("source"),
        handoff=result.get("handoff"),
        score=float(result.get("score") or 0),
        cache_hit=bool(result.get("cache_hit")),
        latency_ms=int(result.get("latency_ms") or 0),
    )


async def _sse_chunks(result: dict[str, Any]) -> AsyncIterator[bytes]:
    """Stream reply as SSE: meta → token chunks → done."""

    def event(name: str, data: dict[str, Any]) -> bytes:
        return f"event: {name}\ndata: {json.dumps(data)}\n\n".encode()

    yield event(
        "meta",
        {
            "conversation_id": result["conversation_id"],
            "trace_id": result["trace_id"],
            "decision": result["decision"],
            "source": result.get("source"),
            "handoff": result.get("handoff"),
        },
    )
    reply = result.get("reply") or ""
    # Chunk for perceived streaming without holding the LLM stream open yet
    step = max(12, len(reply) // 8 or 1)
    for i in range(0, len(reply), step):
        yield event("token", {"text": reply[i : i + step]})
        await asyncio.sleep(0.01)
    yield event(
        "done",
        {
            "reply": reply,
            "latency_ms": result.get("latency_ms"),
            "cache_hit": result.get("cache_hit"),
            "score": result.get("score"),
        },
    )


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[WidgetCtx, Depends(resolve_widget_tenant)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> StreamingResponse:
    tenant, _config = ctx
    result = await run_chat_turn(
        session,
        tenant_id=tenant.id,
        question=body.question,
        language=body.language,
        channel="widget",
        settings=settings,
        conversation_id=body.conversation_id,
    )
    await session.commit()

    async def gen() -> AsyncIterator[bytes]:
        if await request.is_disconnected():
            return
        async for chunk in _sse_chunks(result):
            yield chunk

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/feedback")
async def submit_feedback(
    body: FeedbackRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[WidgetCtx, Depends(resolve_widget_tenant)],
) -> dict[str, str]:
    tenant, _config = ctx
    session.add(
        Feedback(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            trace_id=body.trace_id,
            conversation_id=body.conversation_id,
            rating=body.rating,
            reason=body.reason,
        )
    )
    await session.commit()
    return {"status": "ok"}
