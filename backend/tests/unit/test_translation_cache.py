"""Translation provider and cache helpers."""

from __future__ import annotations

from uuid import uuid4

import pytest

from amakuru.core.settings import get_settings
from amakuru.modules.generation.cache import ReplyCache, cache_key, normalise_question
from amakuru.modules.generation.translation import (
    PassthroughTranslation,
    build_translation_provider,
)


def test_normalise_question() -> None:
    assert normalise_question("  Hello   World  ") == "hello world"


def test_cache_key_stable() -> None:
    tid = uuid4()
    a = cache_key(tenant_id=tid, language="en", question="What fees?")
    b = cache_key(tenant_id=tid, language="en", question="what   fees?")
    assert a == b


@pytest.mark.asyncio
async def test_passthrough_translate_and_detect() -> None:
    tx = PassthroughTranslation()
    assert await tx.detect("hello there") == "en"
    result = await tx.translate(
        "Hello",
        source_lang="en",
        target_lang="lg",
        source_texts_for_firewall=["Hello"],
    )
    assert result.status == "machine"
    assert result.firewall_ok


@pytest.mark.asyncio
async def test_reply_cache_roundtrip() -> None:
    settings = get_settings()
    cache = ReplyCache(settings)
    tid = uuid4()
    payload = {"reply": "hi", "decision": "greeting", "score": 0.0}
    await cache.set(tenant_id=tid, language="en", question="hello", payload=payload)
    got = await cache.get(tenant_id=tid, language="en", question="hello")
    assert got is not None
    assert got["reply"] == "hi"
    await cache.bump_knowledge_epoch(tid)
    assert await cache.get(tenant_id=tid, language="en", question="hello") is None
    await cache.close()


def test_build_translation_provider() -> None:
    settings = get_settings()
    tx = build_translation_provider(settings)
    assert tx is not None
