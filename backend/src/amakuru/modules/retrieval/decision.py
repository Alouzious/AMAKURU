"""Decision policy after retrieval/rerank (Phase 2 — no LLM composition yet)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from amakuru.core.settings import Settings
from amakuru.modules.retrieval.hybrid import Candidate

_GREETING = {
    "hi",
    "hello",
    "hey",
    "thanks",
    "thank you",
    "good morning",
    "good afternoon",
    "ok",
    "okay",
}


class Decision(StrEnum):
    GREETING = "greeting"
    VERBATIM = "verbatim"
    COMPOSE = "compose"
    CLARIFY = "clarify"
    HANDOFF = "handoff"


@dataclass
class DecisionResult:
    decision: Decision
    top: Candidate | None
    score: float
    reason: str


def is_greeting(question: str) -> bool:
    cleaned = " ".join(question.lower().strip().split())
    return cleaned in _GREETING or cleaned.rstrip("!.") in _GREETING


def decide(question: str, candidates: list[Candidate], settings: Settings) -> DecisionResult:
    if is_greeting(question):
        return DecisionResult(Decision.GREETING, None, 0.0, "small_talk")

    if not candidates:
        return DecisionResult(Decision.HANDOFF, None, 0.0, "no_candidates")

    top = candidates[0]
    score = top.rerank_score if top.rerank_score is not None else top.score

    if top.escalate_to_human:
        return DecisionResult(Decision.HANDOFF, top, score, "escalate_to_human")

    if top.verbatim_only or score >= settings.score_verbatim_threshold:
        return DecisionResult(Decision.VERBATIM, top, score, "verbatim_threshold_or_flag")

    if score >= settings.score_answer_threshold:
        # Composition arrives in Phase 3; Phase 2 still returns the approved text path
        # tagged as compose so eval can distinguish threshold bands.
        return DecisionResult(Decision.COMPOSE, top, score, "answer_threshold")

    if score >= settings.score_clarify_threshold:
        # Clarify when near-ties differ mainly by applicability — simplified check:
        if (
            len(candidates) > 1
            and abs((candidates[1].rerank_score or candidates[1].score) - score) < 0.08
        ):
            return DecisionResult(Decision.CLARIFY, top, score, "near_tie")
        return DecisionResult(Decision.CLARIFY, top, score, "clarify_threshold")

    return DecisionResult(Decision.HANDOFF, top, score, "below_clarify")
