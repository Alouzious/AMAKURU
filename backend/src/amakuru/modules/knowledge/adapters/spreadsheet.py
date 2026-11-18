"""Spreadsheet adapter — reads local/uploaded tabular content via config."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from amakuru.modules.knowledge.adapters.base import MappedRow
from amakuru.modules.knowledge.importing import apply_mapping, parse_tabular


class SpreadsheetAdapter:
    async def fetch_rows(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        path = config.get("path")
        content_b64 = config.get("content_base64")
        filename = str(config.get("filename") or "import.csv")
        if content_b64:
            import base64

            content = base64.b64decode(content_b64)
        elif path:
            content = Path(path).read_bytes()
        else:
            raise ValueError("spreadsheet adapter requires path or content_base64")
        _headers, rows = parse_tabular(content, filename)
        return rows

    def map_row(self, row: dict[str, Any], field_mapping: dict[str, str]) -> MappedRow:
        mapped = apply_mapping(row, field_mapping)
        out: MappedRow = {}
        for key, value in mapped.items():
            out[key] = "" if value is None else str(value)  # type: ignore[literal-required]
        return out
