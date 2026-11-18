"""SQL database adapter: pull Q&A rows from an external Postgres/MySQL/SQLite DB.

Config example:
{
  "dsn": "postgresql+psycopg://user:pass@host:5432/uni_faq",
  "query": "SELECT question AS q, answer AS a, office AS office_name FROM faq_items"
}
Field mapping then maps q → question_raw, a → official_answer, etc.

Everything lands as drafts needing approval unless a trusted sync policy is set later.
"""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

from amakuru.modules.knowledge.adapters.base import MappedRow
from amakuru.modules.knowledge.importing import apply_mapping

_BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def _assert_dsn_allowed(dsn: str, *, allow_private: bool) -> None:
    if "://" not in dsn:
        raise ValueError("sql_db dsn must be a SQLAlchemy URL (e.g. postgresql+psycopg://...)")
    scheme = dsn.split("://", 1)[0].lower()
    if not any(scheme.startswith(p) for p in ("postgresql", "postgres", "mysql", "sqlite")):
        raise ValueError("Only postgresql, mysql, or sqlite DSNs are allowed")
    if scheme.startswith("sqlite"):
        return
    parsed = urlparse(dsn.replace("postgresql+psycopg", "postgresql").replace("postgres+psycopg", "postgres"))
    host = (parsed.hostname or "").lower()
    if allow_private:
        return
    if host in _BLOCKED_HOSTS or host.endswith(".local") or host.startswith("10."):
        raise ValueError("Private DB hosts blocked (set ALLOW_PRIVATE_DB_CONNECTORS=true for campus LAN)")
    if host.startswith("192.168.") or host.startswith("172."):
        raise ValueError("Private DB hosts blocked (set ALLOW_PRIVATE_DB_CONNECTORS=true for campus LAN)")


def _fetch_sync(dsn: str, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    engine = create_engine(dsn, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            result = conn.execute(text(query), params)
            rows = result.mappings().all()
            return [dict(r) for r in rows]
    finally:
        engine.dispose()


class SqlDbAdapter:
    def __init__(self, *, allow_private: bool = False) -> None:
        self.allow_private = allow_private

    async def fetch_rows(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        dsn = str(config.get("dsn") or "").strip()
        query = str(config.get("query") or "").strip()
        if not dsn or not query:
            raise ValueError("sql_db adapter requires dsn and query")
        if ";" in query.rstrip(";"):
            raise ValueError("Only a single SELECT query is allowed")
        lowered = query.lower().lstrip()
        if not lowered.startswith("select") and not lowered.startswith("with"):
            raise ValueError("sql_db query must be SELECT (or WITH ... SELECT)")
        _assert_dsn_allowed(dsn, allow_private=self.allow_private)
        params = dict(config.get("params") or {})
        return await asyncio.to_thread(_fetch_sync, dsn, query, params)

    def map_row(self, row: dict[str, Any], field_mapping: dict[str, str]) -> MappedRow:
        # Allow direct club-column names without mapping.
        normalized = {str(k): ("" if v is None else v) for k, v in row.items()}
        mapped = apply_mapping(normalized, field_mapping) if field_mapping else normalized
        out: MappedRow = {}
        for key, value in mapped.items():
            out[key] = "" if value is None else str(value)  # type: ignore[literal-required]
        return out
