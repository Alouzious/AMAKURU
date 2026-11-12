"""Channel chat turn orchestration."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from amakuru.core.db import set_tenant
from amakuru.core.settings import Settings
from amakuru.modules.billing.entitlements import assert_conversation_quota
from amakuru.modules.billing.metering import record_answered_turn
from amakuru.modules.channels.handoff import enqueue_unanswered, handoff_card, load_office
from amakuru.modules.channels.models import Conversation, Message
from amakuru.modules.knowledge.models import AnswerVersion, Office
from amakuru.modules.retrieval.providers.embeddings import build_embedding_provider
from amakuru.modules.retrieval.providers.reranker import build_reranker
from amakuru.modules.retrieval.service import retrieve
from amakuru.modules.retrieval.vector_store import PgVectorStore


async def get_or_create_conversation(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    channel: str,
    conversation_id: uuid.UUID | None,
    external_thread_id: str | None,
    language: str,
) -> Conversation:
    if conversation_id is not None:
        result = await session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.tenant_id == tenant_id,
            )
        )
        found = result.scalar_one_or_none()
        if found is not None:
            return found
    if external_thread_id:
        result = await session.execute(
            select(Conversation).where(
                Conversation.tenant_id == tenant_id,
                Conversation.channel == channel,
                Conversation.external_thread_id == external_thread_id,
            )
        )
        found = result.scalar_one_or_none()
        if found is not None:
            return found
    conv = Conversation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        channel=channel,
        external_thread_id=external_thread_id,
        language=language,
        metadata_={},
    )
    session.add(conv)
    await session.flush()
    return conv


async def run_chat_turn(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    question: str,
    language: str,
    channel: str,
    settings: Settings,
    conversation_id: uuid.UUID | None = None,
    external_thread_id: str | None = None,
) -> dict[str, Any]:
    await set_tenant(session, tenant_id)
    await assert_conversation_quota(session, tenant_id)
    conv = await get_or_create_conversation(
        session,
        tenant_id=tenant_id,
        channel=channel,
        conversation_id=conversation_id,
        external_thread_id=external_thread_id,
        language=language,
    )

    session.add(
        Message(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            conversation_id=conv.id,
            role="user",
            content=question,
            language=language,
            meta={"channel": channel},
        )
    )

    embedder = build_embedding_provider(settings)
    reranker = build_reranker(settings)
    store = PgVectorStore()
    result = await retrieve(
        session,
        tenant_id=tenant_id,
        question=question,
        language=language,
        settings=settings,
        embedder=embedder,
        reranker=reranker,
        store=store,
    )

    office: Office | None = None
    source: dict[str, Any] | None = None
    if result.get("entry_id") and result.get("version_id"):
        ver = await session.execute(
            select(AnswerVersion).where(AnswerVersion.id == uuid.UUID(result["version_id"]))
        )
        version = ver.scalar_one_or_none()
        if version is not None:
            office = await load_office(session, tenant_id=tenant_id, office_id=None)
            # Prefer owning office from candidates
            for cand in result.get("candidates") or []:
                if cand.get("entry_id") == result["entry_id"] and cand.get("office_id"):
                    office = await load_office(
                        session,
                        tenant_id=tenant_id,
                        office_id=uuid.UUID(cand["office_id"]),
                    )
                    break
            source = {
                "office_name": office.name if office else None,
                "last_verified": version.last_verified.isoformat()
                if version.last_verified
                else None,
                "entry_id": result["entry_id"],
                "version_id": result["version_id"],
            }

    handoff: dict[str, Any] | None = None
    if result["decision"] == "handoff":
        office_id = None
        if result.get("candidates"):
            oid = result["candidates"][0].get("office_id")
            office_id = uuid.UUID(oid) if oid else None
        office = await load_office(session, tenant_id=tenant_id, office_id=office_id)
        handoff = handoff_card(office, reply=result.get("reply") or "")
        await enqueue_unanswered(
            session,
            tenant_id=tenant_id,
            question=question,
            language=language,
            channel=channel,
            office_id=office.id if office else None,
            conversation_id=conv.id,
            trace_id=uuid.UUID(result["trace_id"]),
        )
        if office:
            reply = (
                f"{result.get('reply') or 'I am not sure.'}\n\n"
                f"Please contact {office.name}"
                + (f" ({office.contact_person})" if office.contact_person else "")
                + (f" — {office.phone}" if office.phone else "")
                + (f" / {office.email}" if office.email else "")
                + "."
            )
            result["reply"] = reply

    session.add(
        Message(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            conversation_id=conv.id,
            role="assistant",
            content=result.get("reply") or "",
            language=language,
            trace_id=uuid.UUID(result["trace_id"]),
            meta={
                "decision": result["decision"],
                "source": source,
                "handoff": handoff,
            },
        )
    )
    await record_answered_turn(
        session,
        tenant_id=tenant_id,
        tokens=int(result.get("tokens") or 0),
        estimated_cost_usd=float(result.get("estimated_cost_usd") or 0),
        channel=channel,
    )
    await session.flush()

    return {
        **result,
        "conversation_id": str(conv.id),
        "source": source,
        "handoff": handoff,
        "channel": channel,
    }
