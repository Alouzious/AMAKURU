"""Adapter protocol for external knowledge sources."""

from __future__ import annotations

from typing import Any, Protocol, TypedDict


class MappedRow(TypedDict, total=False):
    question_raw: str
    asker_type: str
    language: str
    channel: str
    category: str
    subcategory: str
    frequency: str
    season: str
    official_answer: str
    source_document: str
    owner_office: str
    last_verified: str
    valid_until: str
    escalate_to_human: str
    collector: str
    date_collected: str


class KnowledgeAdapter(Protocol):
    """Fetch rows and map them into the club column shape. Sync always lands as drafts."""

    async def fetch_rows(self, config: dict[str, Any]) -> list[dict[str, Any]]: ...

    def map_row(self, row: dict[str, Any], field_mapping: dict[str, str]) -> MappedRow: ...
