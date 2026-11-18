"""Number firewall — generated/translated text may not invent protected tokens."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Fees, dates, deadlines, %, phones, emails, URLs, currency amounts.
_PROTECTED = re.compile(
    r"""
    (?:https?://[^\s<>"']+)                         # URLs
    | (?:www\.[^\s<>"']+)
    | (?:[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})  # emails
    | (?:\+?\d[\d\s().-]{6,}\d)                     # phones / long digit runs
    | (?:UGX|USD|EUR|GBP)\s*[\d,]+(?:\.\d+)?        # currency
    | (?:[\d,]+(?:\.\d+)?\s*(?:UGX|USD|EUR|GBP|%))  # amount + unit
    | (?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4})             # dates
    | (?:\d{4}-\d{2}-\d{2})                         # ISO dates
    | (?:\d+(?:\.\d+)?%)                            # percentages
    | (?:\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b)          # grouped numbers
    | (?:\b\d+\.\d+\b)                              # decimals
    | (?:\b\d{4,}\b)                                # long bare numbers (fees etc.)
    """,
    re.VERBOSE | re.IGNORECASE,
)


@dataclass(frozen=True)
class FirewallResult:
    ok: bool
    text: str
    invented: list[str]
    used_fallback: bool


def extract_protected_tokens(text: str) -> set[str]:
    return {m.group(0) for m in _PROTECTED.finditer(text)}


def number_firewall(*, source_texts: list[str], candidate: str) -> FirewallResult:
    """Every protected token in candidate must appear character-for-character in sources.

    On failure, caller should discard `candidate` and return approved source text.
    """
    allowed: set[str] = set()
    for src in source_texts:
        allowed |= extract_protected_tokens(src)
    found = extract_protected_tokens(candidate)
    invented = sorted(t for t in found if t not in allowed)
    if invented:
        return FirewallResult(ok=False, text=candidate, invented=invented, used_fallback=False)
    return FirewallResult(ok=True, text=candidate, invented=[], used_fallback=False)


def lock_protected_placeholders(text: str) -> tuple[str, dict[str, str]]:
    """Replace protected tokens with placeholders for translation."""
    mapping: dict[str, str] = {}
    counter = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal counter
        key = f"⟦P{counter}⟧"
        mapping[key] = m.group(0)
        counter += 1
        return key

    return _PROTECTED.sub(repl, text), mapping


def unlock_protected_placeholders(text: str, mapping: dict[str, str]) -> str:
    out = text
    for key, value in mapping.items():
        out = out.replace(key, value)
    return out
