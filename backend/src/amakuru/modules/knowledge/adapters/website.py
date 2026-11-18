"""Website suggestion miner: crawl public pages and propose draft Q&A pairs.

Does not publish automatically. Proposals use page title/heading as the question
and nearby paragraph text as a suggested answer, with the URL as source_document.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from amakuru.modules.knowledge.adapters.base import MappedRow
from amakuru.modules.knowledge.importing import apply_mapping

_BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.headings: list[str] = []
        self.paragraphs: list[str] = []
        self.links: list[str] = []
        self._capture: str | None = None
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"title", "h1", "h2", "h3", "p"}:
            self._capture = tag
            self._buf = []
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if self._capture != tag:
            return
        text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        if tag == "title" and text:
            self.title = text
        elif tag in {"h1", "h2", "h3"} and text:
            self.headings.append(text)
        elif tag == "p" and text and len(text) > 40:
            self.paragraphs.append(text)
        self._capture = None
        self._buf = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buf.append(data)


def _assert_public_url(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http/https URLs are allowed")
    if host in _BLOCKED_HOSTS or host.endswith(".local") or host.startswith("10."):
        raise ValueError("Private or local URLs are blocked")
    if host.startswith("192.168.") or host.startswith("172."):
        raise ValueError("Private or local URLs are blocked")


class WebsiteAdapter:
    async def fetch_rows(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        start = str(config.get("start_url") or "").strip()
        if not start:
            raise ValueError("website adapter requires start_url")
        _assert_public_url(start)
        max_pages = min(int(config.get("max_pages") or 15), 40)
        same_host = bool(config.get("same_host_only", True))
        start_host = urlparse(start).hostname

        seen: set[str] = set()
        queue = [start]
        rows: list[dict[str, Any]] = []

        async with httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": "AmakuruBot/0.1 (+knowledge-suggestions)"},
        ) as client:
            while queue and len(seen) < max_pages:
                url = queue.pop(0)
                if url in seen:
                    continue
                seen.add(url)
                try:
                    resp = await client.get(url)
                except httpx.HTTPError:
                    continue
                ctype = resp.headers.get("content-type", "")
                if resp.status_code >= 400 or "text/html" not in ctype:
                    continue
                parser = _PageParser()
                try:
                    parser.feed(resp.text)
                except Exception:  # noqa: BLE001
                    continue

                body = " ".join(parser.paragraphs[:3]).strip()
                question = parser.headings[0] if parser.headings else parser.title
                if question and body:
                    rows.append(
                        {
                            "question_raw": question[:500],
                            "official_answer": body[:4000],
                            "source_document": url,
                            "category": "website",
                            "subcategory": "crawl",
                            "language": "en",
                            "owner_office": str(config.get("default_office") or "Webmaster"),
                        }
                    )

                for href in parser.links:
                    abs_url = urljoin(url, href).split("#", 1)[0]
                    p = urlparse(abs_url)
                    if p.scheme not in {"http", "https"}:
                        continue
                    if same_host and p.hostname != start_host:
                        continue
                    if abs_url not in seen and len(queue) + len(seen) < max_pages * 3:
                        queue.append(abs_url)

        return rows

    def map_row(self, row: dict[str, Any], field_mapping: dict[str, str]) -> MappedRow:
        mapped = apply_mapping(row, field_mapping) if field_mapping else row
        out: MappedRow = {}
        for key, value in mapped.items():
            out[key] = "" if value is None else str(value)  # type: ignore[literal-required]
        return out
