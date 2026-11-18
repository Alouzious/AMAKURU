"""Simple circuit breaker for LLM providers."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    recovery_seconds: float = 30.0
    failures: int = 0
    opened_at: float | None = None
    _lock_note: str = field(default="", repr=False)

    def allow(self) -> bool:
        if self.opened_at is None:
            return True
        # Half-open after recovery window
        return time.monotonic() - self.opened_at >= self.recovery_seconds

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.opened_at = time.monotonic()

    @property
    def is_open(self) -> bool:
        return not self.allow()
