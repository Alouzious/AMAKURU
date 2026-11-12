"""Generic REST/JSON adapter. Everything lands as draft needing approval."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from amakuru.modules.knowledge.adapters.base import MappedRow
from amakuru.modules.knowledge.importing import apply_mapping

_BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def _assert_public_url(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http/https URLs are allowed")
    if host in _BLOCKED_HOSTS or host.endswith(".local") or host.startswith("10."):
        raise ValueError("Private or local URLs are blocked")
    if host.startswith("192.168.") or host.startswith("172."):
        # Broad SSRF guard for common private ranges.
        raise ValueError("Private or local URLs are blocked")


class RestJsonAdapter:
    async def fetch_rows(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        url = str(config.get("url") or "")
        if not url:
            raise ValueError("rest_json adapter requires url")
        _assert_public_url(url)
        headers = dict(config.get("headers") or {})
        items_path = str(config.get("items_path") or "")
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            payload = resp.json()

        if items_path:
            for part in items_path.split("."):
                if part:
                    payload = payload[part]
        if not isinstance(payload, list):
            raise ValueError("JSON payload must be a list of objects (or items_path to a list)")
        return [row for row in payload if isinstance(row, dict)]

    def map_row(self, row: dict[str, Any], field_mapping: dict[str, str]) -> MappedRow:
        mapped = apply_mapping(row, field_mapping)
        out: MappedRow = {}
        for key, value in mapped.items():
            out[key] = "" if value is None else str(value)  # type: ignore[literal-required]
        return out
