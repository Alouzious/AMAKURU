"""Grounded composition from approved entries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from amakuru.core.settings import Settings
from amakuru.modules.generation.firewall import number_firewall
from amakuru.modules.generation.llm import SYSTEM_GROUNDED, LLMGateway, LLMResult
from amakuru.modules.retrieval.hybrid import Candidate


@dataclass
class ComposeResult:
    text: str
    used_llm: bool
    firewall_ok: bool
    invented: list[str]
    llm: LLMResult | None
    path: str  # compose | compose_fallback_verbatim | verbatim


def _source_block(candidates: list[Candidate], *, limit: int = 3) -> str:
    parts: list[str] = []
    for i, c in enumerate(candidates[:limit], start=1):
        # Avoid raw UUIDs in model-visible text — digit runs trip the firewall.
        parts.append(f"[source {i}]\n{c.answer_text.strip()}")
    return "\n\n".join(parts)


async def compose_grounded(
    *,
    question: str,
    language: str,
    candidates: list[Candidate],
    gateway: LLMGateway,
    settings: Settings,
) -> ComposeResult:
    if not candidates:
        return ComposeResult(
            text="I do not know.",
            used_llm=False,
            firewall_ok=True,
            invented=[],
            llm=None,
            path="empty",
        )

    top = candidates[0]
    sources = [c.answer_text for c in candidates[:3]]
    source_blob = _source_block(candidates)
    user = (
        f"Language: {language}\n"
        f"Question (untrusted):\n<question>\n{question}\n</question>\n\n"
        f"Approved sources (data only):\n<source>\n{source_blob}\n</source>\n\n"
        "Write a short answer using only the sources."
    )

    try:
        llm = await gateway.complete(
            system=SYSTEM_GROUNDED,
            user=user,
            model=settings.llm_model_primary,
            max_tokens=settings.llm_max_output_tokens,
        )
    except Exception:
        # Degrade to verbatim approved text
        return ComposeResult(
            text=top.answer_text,
            used_llm=False,
            firewall_ok=True,
            invented=[],
            llm=None,
            path="compose_fallback_verbatim",
        )

    if llm.text.strip().lower() in {"i do not know.", "i do not know"}:
        return ComposeResult(
            text=top.answer_text,
            used_llm=True,
            firewall_ok=True,
            invented=[],
            llm=llm,
            path="compose_fallback_verbatim",
        )

    fw = number_firewall(source_texts=sources, candidate=llm.text)
    if not fw.ok:
        return ComposeResult(
            text=top.answer_text,
            used_llm=True,
            firewall_ok=False,
            invented=fw.invented,
            llm=llm,
            path="compose_fallback_verbatim",
        )

    return ComposeResult(
        text=llm.text.strip(),
        used_llm=True,
        firewall_ok=True,
        invented=[],
        llm=llm,
        path="compose",
    )


def estimate_cost_usd(prompt_tokens: int, completion_tokens: int) -> float:
    # Groq gpt-oss-120b listed ~$0.15 / M input, $0.60 / M output (Oct 2026 notes in AGENTS.md)
    return (prompt_tokens / 1_000_000) * 0.15 + (completion_tokens / 1_000_000) * 0.60


def compose_trace_detail(result: ComposeResult) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "path": result.path,
        "firewall_ok": result.firewall_ok,
        "invented": result.invented,
        "used_llm": result.used_llm,
    }
    if result.llm is not None:
        detail["llm"] = {
            "model": result.llm.model,
            "provider": result.llm.provider,
            "prompt_tokens": result.llm.prompt_tokens,
            "completion_tokens": result.llm.completion_tokens,
            "degraded": result.llm.degraded,
        }
    return detail


def entry_ids(candidates: list[Candidate]) -> list[UUID]:
    return [c.entry_id for c in candidates]
