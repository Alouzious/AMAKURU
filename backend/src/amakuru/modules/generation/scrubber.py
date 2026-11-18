"""Personal-data scrubber — remove PII before storage or model calls."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Uganda-ish national ID patterns (alphanumeric blocks) + generic card / phone / email.
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
# Prefer international (+) or local leading-0 forms to avoid scrubbing fee amounts.
_PHONE = re.compile(
    r"(?<!\w)(?:\+\d{1,3}[\s-]?(?:\d[\s-]?){7,14}\d|0\d{2,3}[\s-]?\d{3}[\s-]?\d{3,4})(?!\w)"
)
_CARD = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_NIN = re.compile(r"\b[A-Z]{2}\d{8}[A-Z0-9]{4}\b", re.I)  # common UG NIN shape
_PLACEHOLDER = {
    "email": "[EMAIL]",
    "phone": "[PHONE]",
    "card": "[CARD]",
    "nin": "[NIN]",
}


@dataclass(frozen=True)
class ScrubResult:
    text: str
    redactions: int


def scrub_personal_data(text: str) -> ScrubResult:
    """Return scrubbed text; count how many substitutions were made."""
    redactions = 0
    out = text

    def _sub(pattern: re.Pattern[str], label: str, value: str) -> str:
        nonlocal redactions

        def repl(_m: re.Match[str]) -> str:
            nonlocal redactions
            redactions += 1
            return _PLACEHOLDER[label]

        return pattern.sub(repl, value)

    out = _sub(_EMAIL, "email", out)
    out = _sub(_CARD, "card", out)
    out = _sub(_NIN, "nin", out)
    out = _sub(_PHONE, "phone", out)
    return ScrubResult(text=out, redactions=redactions)
