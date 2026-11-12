"""Retrieval + generation query pipeline with traces."""

from __future__ import annotations

import time
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from amakuru.core.settings import Settings
from amakuru.modules.generation.cache import ReplyCache, normalise_question
from amakuru.modules.generation.compose import (
    compose_grounded,
    compose_trace_detail,
    estimate_cost_usd,
)
from amakuru.modules.generation.firewall import number_firewall
from amakuru.modules.generation.llm import LLMGateway, build_llm_gateway
from amakuru.modules.generation.scrubber import scrub_personal_data
from amakuru.modules.generation.translation import TranslationProvider, build_translation_provider
from amakuru.modules.retrieval.decision import Decision, decide
from amakuru.modules.retrieval.hybrid import Candidate, candidate_to_dict, hybrid_retrieve
from amakuru.modules.retrieval.models import QueryTrace
from amakuru.modules.retrieval.providers.embeddings import EmbeddingProvider
from amakuru.modules.retrieval.providers.reranker import RerankerProvider
from amakuru.modules.retrieval.vector_store import PgVectorStore


async def retrieve(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    question: str,
    language: str,
    settings: Settings,
    embedder: EmbeddingProvider,
    reranker: RerankerProvider,
    store: PgVectorStore,
    gateway: LLMGateway | None = None,
    translator: TranslationProvider | None = None,
    cache: ReplyCache | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    steps: list[dict[str, Any]] = []
    tokens = 0
    cost = 0.0
    cache_hit = False

    raw = question.strip()[:2000]
    steps.append({"step": "normalise", "length": len(raw)})

    scrubbed = scrub_personal_data(raw)
    q = scrubbed.text
    steps.append({"step": "scrub", "redactions": scrubbed.redactions})

    llm = gateway or build_llm_gateway(settings)
    tx = translator or build_translation_provider(settings)
    reply_cache = cache or ReplyCache(settings)

    detected = language
    if language in {"auto", ""}:
        detected = await tx.detect(q)
        steps.append({"step": "detect_language", "language": detected})
    else:
        detected = language

    cached = await reply_cache.get(tenant_id=tenant_id, language=detected, question=q)
    if cached is not None:
        cache_hit = True
        steps.append({"step": "cache", "hit": True})
        latency_ms = int((time.perf_counter() - started) * 1000)
        trace = QueryTrace(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            question=q,
            language=detected,
            steps=steps + list(cached.get("steps") or []),
            candidates=list(cached.get("candidates") or []),
            decision=str(cached.get("decision") or "cache"),
            entry_id=uuid.UUID(cached["entry_id"]) if cached.get("entry_id") else None,
            version_id=uuid.UUID(cached["version_id"]) if cached.get("version_id") else None,
            latency_ms=latency_ms,
            tokens=int(cached.get("tokens") or 0),
            estimated_cost_usd=Decimal(str(cached.get("estimated_cost_usd") or 0)),
            cache_hit=True,
        )
        session.add(trace)
        await session.flush()
        return {
            "trace_id": str(trace.id),
            "decision": trace.decision,
            "reason": str(cached.get("reason") or "cache_hit"),
            "score": float(cached.get("score") or 0),
            "entry_id": cached.get("entry_id"),
            "version_id": cached.get("version_id"),
            "reply": cached.get("reply"),
            "candidates": cached.get("candidates") or [],
            "latency_ms": latency_ms,
            "steps": steps,
            "cache_hit": True,
            "machine_translated": bool(cached.get("machine_translated")),
        }

    steps.append({"step": "cache", "hit": False, "norm": normalise_question(q)})

    vectors = await embedder.embed([q])
    steps.append({"step": "embed", "model": embedder.model_id})

    candidates = await hybrid_retrieve(
        session,
        store,
        tenant_id=tenant_id,
        query=q,
        dense=vectors[0],
        model_id=embedder.model_id,
        top_k=settings.retrieval_top_k,
    )
    steps.append({"step": "hybrid", "candidates": len(candidates)})

    if candidates:
        docs = [
            f"{c.question_text or ''}\n{c.answer_text}".strip()
            for c in candidates[: settings.rerank_candidates]
        ]
        reranked = await reranker.rerank(q, docs, top_k=min(settings.retrieval_final_k, len(docs)))
        ordered: list[Candidate] = []
        for idx, score in reranked:
            c = candidates[idx]
            c.rerank_score = score
            c.score = score
            ordered.append(c)
        seen = {id(c) for c in ordered}
        for c in candidates:
            if id(c) not in seen:
                ordered.append(c)
        candidates = ordered[: settings.retrieval_final_k]
        steps.append({"step": "rerank", "kept": len(candidates)})

    decision = decide(q, candidates, settings)
    steps.append(
        {
            "step": "decision",
            "decision": decision.decision.value,
            "reason": decision.reason,
            "score": decision.score,
        }
    )

    reply_text: str | None = None
    machine_translated = False
    source_texts = [c.answer_text for c in candidates[:3]] if candidates else []

    if decision.decision == Decision.GREETING:
        reply_text = "Hello! How can I help you with university information today?"
    elif decision.decision == Decision.VERBATIM and decision.top:
        reply_text = decision.top.answer_text
        steps.append({"step": "reply", "path": "verbatim"})
    elif decision.decision == Decision.COMPOSE and decision.top:
        composed = await compose_grounded(
            question=q,
            language=detected,
            candidates=candidates,
            gateway=llm,
            settings=settings,
        )
        reply_text = composed.text
        steps.append({"step": "compose", **compose_trace_detail(composed)})
        if composed.llm is not None:
            tokens = composed.llm.prompt_tokens + composed.llm.completion_tokens
            cost = estimate_cost_usd(composed.llm.prompt_tokens, composed.llm.completion_tokens)
        # Firewall already applied inside compose; re-check before return
        fw = number_firewall(source_texts=source_texts, candidate=reply_text)
        if not fw.ok:
            reply_text = decision.top.answer_text
            steps.append({"step": "firewall", "ok": False, "invented": fw.invented})
        else:
            steps.append({"step": "firewall", "ok": True})
    elif decision.decision == Decision.CLARIFY:
        reply_text = (
            "I found a few close matches. Could you share a bit more detail "
            "(for example programme or student type)?"
        )
    else:
        reply_text = (
            "I am not sure I have an approved answer for that. "
            "Please contact the relevant university office."
        )

    # Translate when user language is not English and we have an answer from the bank
    if (
        reply_text
        and detected != "en"
        and decision.decision in {Decision.VERBATIM, Decision.COMPOSE}
    ):
        tr = await tx.translate(
            reply_text,
            source_lang="en",
            target_lang=detected,
            source_texts_for_firewall=source_texts or [reply_text],
        )
        steps.append(
            {
                "step": "translate",
                "provider": tr.provider,
                "status": tr.status,
                "firewall_ok": tr.firewall_ok,
                "invented": tr.invented,
            }
        )
        if tr.firewall_ok:
            reply_text = tr.text
            machine_translated = tr.status == "machine"
        else:
            # Keep approved English source if translation invented protected tokens
            machine_translated = False

    latency_ms = int((time.perf_counter() - started) * 1000)
    cand_dicts = [candidate_to_dict(c) for c in candidates]
    payload = {
        "decision": decision.decision.value,
        "reason": decision.reason,
        "score": decision.score,
        "entry_id": str(decision.top.entry_id) if decision.top else None,
        "version_id": str(decision.top.version_id) if decision.top else None,
        "reply": reply_text,
        "candidates": cand_dicts,
        "tokens": tokens,
        "estimated_cost_usd": cost,
        "steps": steps,
        "machine_translated": machine_translated,
    }

    if decision.decision in {Decision.VERBATIM, Decision.COMPOSE, Decision.GREETING}:
        await reply_cache.set(tenant_id=tenant_id, language=detected, question=q, payload=payload)

    trace = QueryTrace(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        question=q,
        language=detected,
        steps=steps,
        candidates=cand_dicts,
        decision=decision.decision.value,
        entry_id=decision.top.entry_id if decision.top else None,
        version_id=decision.top.version_id if decision.top else None,
        latency_ms=latency_ms,
        tokens=tokens,
        estimated_cost_usd=Decimal(str(round(cost, 8))),
        cache_hit=cache_hit,
    )
    session.add(trace)
    await session.flush()

    return {
        "trace_id": str(trace.id),
        "decision": decision.decision.value,
        "reason": decision.reason,
        "score": decision.score,
        "entry_id": str(decision.top.entry_id) if decision.top else None,
        "version_id": str(decision.top.version_id) if decision.top else None,
        "reply": reply_text,
        "candidates": cand_dicts,
        "latency_ms": latency_ms,
        "steps": steps,
        "cache_hit": cache_hit,
        "machine_translated": machine_translated,
        "tokens": tokens,
        "estimated_cost_usd": cost,
    }
