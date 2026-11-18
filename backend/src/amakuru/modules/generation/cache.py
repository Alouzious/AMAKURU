"""Reply cache keyed by tenant + language + normalised question."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, cast
from uuid import UUID

import redis.asyncio as redis

from amakuru.core.settings import Settings

_WS = re.compile(r"\s+")


def normalise_question(text: str) -> str:
    return _WS.sub(" ", text.strip().lower())


def cache_key(*, tenant_id: UUID, language: str, question: str) -> str:
    norm = normalise_question(question)
    digest = hashlib.sha256(norm.encode()).hexdigest()[:32]
    return f"amakuru:reply:{tenant_id}:{language}:{digest}"


def knowledge_epoch_key(tenant_id: UUID) -> str:
    return f"amakuru:knowledge_epoch:{tenant_id}"


class ReplyCache:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: redis.Redis[str] | None = None

    async def _redis(self) -> redis.Redis[str]:
        if self._client is None:
            self._client = redis.from_url(self.settings.redis_url, decode_responses=True)
        return self._client

    async def get(self, *, tenant_id: UUID, language: str, question: str) -> dict[str, Any] | None:
        if not self.settings.enable_semantic_cache:
            return None
        try:
            client = await self._redis()
            raw = await client.get(
                cache_key(tenant_id=tenant_id, language=language, question=question)
            )
            if not raw:
                return None
            parsed = json.loads(raw)
            return cast(dict[str, Any], parsed)
        except Exception:
            return None

    async def set(
        self,
        *,
        tenant_id: UUID,
        language: str,
        question: str,
        payload: dict[str, Any],
    ) -> None:
        if not self.settings.enable_semantic_cache:
            return
        try:
            client = await self._redis()
            await client.set(
                cache_key(tenant_id=tenant_id, language=language, question=question),
                json.dumps(payload),
                ex=self.settings.cache_ttl_seconds,
            )
        except Exception:
            return

    async def bump_knowledge_epoch(self, tenant_id: UUID) -> None:
        """Invalidate tenant reply cache keys after knowledge changes."""
        try:
            client = await self._redis()
            await client.incr(knowledge_epoch_key(tenant_id))
            pattern = f"amakuru:reply:{tenant_id}:*"
            async for key in client.scan_iter(match=pattern, count=100):
                await client.delete(key)
        except Exception:
            return

    async def close(self) -> None:
        if self._client is not None:
            close = getattr(self._client, "aclose", None) or self._client.close
            await close()
            self._client = None
