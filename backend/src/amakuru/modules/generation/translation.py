"""Translation provider interface — Sunbird / Fasiri / passthrough."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

from amakuru.core.settings import Settings
from amakuru.modules.generation.firewall import (
    lock_protected_placeholders,
    number_firewall,
    unlock_protected_placeholders,
)

SUPPORTED = frozenset({"en", "lg", "nyn", "sw"})


@dataclass(frozen=True)
class TranslationResult:
    text: str
    language: str
    provider: str
    status: str  # approved | machine | passthrough
    firewall_ok: bool
    invented: list[str]


class TranslationProvider(Protocol):
    async def detect(self, text: str) -> str: ...

    async def translate(
        self,
        text: str,
        *,
        source_lang: str,
        target_lang: str,
        source_texts_for_firewall: list[str] | None = None,
    ) -> TranslationResult: ...


class PassthroughTranslation:
    async def detect(self, text: str) -> str:
        # Tiny heuristic; Phase 4+ can use Sunbird detection.
        sample = text.lower()
        if any(w in sample for w in ("bulungi", "nsaba", "kiki", "webale")):
            return "lg"
        if any(w in sample for w in ("habari", "asante", "tafadhali")):
            return "sw"
        return "en"

    async def translate(
        self,
        text: str,
        *,
        source_lang: str,
        target_lang: str,
        source_texts_for_firewall: list[str] | None = None,
    ) -> TranslationResult:
        if source_lang == target_lang or target_lang == "en":
            return TranslationResult(
                text=text,
                language=target_lang,
                provider="passthrough",
                status="passthrough",
                firewall_ok=True,
                invented=[],
            )
        # Without a live translator, keep English approved text and mark machine-pending.
        sources = source_texts_for_firewall or [text]
        fw = number_firewall(source_texts=sources, candidate=text)
        return TranslationResult(
            text=text,
            language=target_lang,
            provider="passthrough",
            status="machine",
            firewall_ok=fw.ok,
            invented=fw.invented,
        )


class SunbirdTranslation:
    def __init__(self, settings: Settings, fallback: TranslationProvider) -> None:
        self.settings = settings
        self.fallback = fallback

    async def detect(self, text: str) -> str:
        if not self.settings.sunbird_api_token:
            return await self.fallback.detect(text)
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{self.settings.sunbird_base_url.rstrip('/')}/tasks/language_id",
                    headers={"Authorization": f"Bearer {self.settings.sunbird_api_token}"},
                    json={"text": text},
                )
                if resp.status_code >= 400:
                    return await self.fallback.detect(text)
                data = resp.json()
                lang = str(data.get("language") or data.get("lang") or "en")
                return lang if lang in SUPPORTED else "en"
        except Exception:
            return await self.fallback.detect(text)

    async def translate(
        self,
        text: str,
        *,
        source_lang: str,
        target_lang: str,
        source_texts_for_firewall: list[str] | None = None,
    ) -> TranslationResult:
        if source_lang == target_lang:
            return TranslationResult(
                text=text,
                language=target_lang,
                provider="sunbird",
                status="passthrough",
                firewall_ok=True,
                invented=[],
            )
        if not self.settings.sunbird_api_token or not self.settings.allow_external_ai_calls:
            return await self.fallback.translate(
                text,
                source_lang=source_lang,
                target_lang=target_lang,
                source_texts_for_firewall=source_texts_for_firewall,
            )

        locked, mapping = lock_protected_placeholders(text)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.settings.sunbird_base_url.rstrip('/')}/tasks/translate",
                    headers={"Authorization": f"Bearer {self.settings.sunbird_api_token}"},
                    json={
                        "source_language": source_lang,
                        "target_language": target_lang,
                        "text": locked,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                translated = str(data.get("text") or data.get("translation") or locked)
        except Exception:
            return await self.fallback.translate(
                text,
                source_lang=source_lang,
                target_lang=target_lang,
                source_texts_for_firewall=source_texts_for_firewall,
            )

        unlocked = unlock_protected_placeholders(translated, mapping)
        sources = source_texts_for_firewall or [text]
        fw = number_firewall(source_texts=sources, candidate=unlocked)
        if not fw.ok:
            return TranslationResult(
                text=text,
                language=target_lang,
                provider="sunbird",
                status="machine",
                firewall_ok=False,
                invented=fw.invented,
            )
        return TranslationResult(
            text=unlocked,
            language=target_lang,
            provider="sunbird",
            status="machine",
            firewall_ok=True,
            invented=[],
        )


def build_translation_provider(settings: Settings) -> TranslationProvider:
    passthrough = PassthroughTranslation()
    provider = settings.translation_provider.lower()
    if provider in {"none", "passthrough"}:
        return passthrough
    if provider == "sunbird":
        return SunbirdTranslation(settings, passthrough)
    # fasiri adapter can plug in later; fall back safely
    return passthrough
