"""Smoke tests for sql_db and website adapters (no network for website SSRF checks)."""

from __future__ import annotations

import pytest

from amakuru.modules.knowledge.adapters.sql_db import SqlDbAdapter
from amakuru.modules.knowledge.adapters.website import WebsiteAdapter


@pytest.mark.asyncio
async def test_sql_db_rejects_non_select() -> None:
    adapter = SqlDbAdapter(allow_private=True)
    with pytest.raises(ValueError, match="SELECT"):
        await adapter.fetch_rows(
            {"dsn": "sqlite:///:memory:", "query": "DELETE FROM faq"}
        )


@pytest.mark.asyncio
async def test_sql_db_sqlite_roundtrip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import sqlite3

    db = tmp_path / "faq.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE faq (q TEXT, a TEXT, office TEXT)")
    conn.execute(
        "INSERT INTO faq VALUES (?, ?, ?)",
        ("How do I apply?", "DEMONSTRATION ONLY: Apply online.", "Admissions"),
    )
    conn.commit()
    conn.close()

    adapter = SqlDbAdapter(allow_private=True)
    rows = await adapter.fetch_rows(
        {
            "dsn": f"sqlite:///{db}",
            "query": "SELECT q, a, office FROM faq",
        }
    )
    assert len(rows) == 1
    mapped = adapter.map_row(
        rows[0],
        {"question_raw": "q", "official_answer": "a", "owner_office": "office"},
    )
    assert mapped["question_raw"] == "How do I apply?"
    assert "DEMONSTRATION" in (mapped.get("official_answer") or "")


@pytest.mark.asyncio
async def test_website_blocks_private_url() -> None:
    adapter = WebsiteAdapter()
    with pytest.raises(ValueError, match="Private"):
        await adapter.fetch_rows({"start_url": "http://127.0.0.1/"})
