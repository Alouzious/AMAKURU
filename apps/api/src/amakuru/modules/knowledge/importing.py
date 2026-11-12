"""CSV/Excel import with column mapping for the club dataset format."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from openpyxl import load_workbook
from sqlalchemy.ext.asyncio import AsyncSession

from amakuru.modules.knowledge.models import CLUB_COLUMNS, IngestionJob
from amakuru.modules.knowledge.schemas import ImportPreviewOut, ImportRunOut
from amakuru.modules.knowledge.service import create_draft_from_mapped_row
from amakuru.modules.platform.audit import write_audit


def suggest_mapping(headers: list[str]) -> dict[str, str]:
    """Map source headers to club columns by case-insensitive name match."""
    normalized = {h.strip().lower().replace(" ", "_"): h for h in headers}
    mapping: dict[str, str] = {}
    for col in CLUB_COLUMNS:
        if col in normalized:
            mapping[col] = normalized[col]
        elif col.lower() in normalized:
            mapping[col] = normalized[col.lower()]
    return mapping


def parse_tabular(content: bytes, filename: str) -> tuple[list[str], list[dict[str, Any]]]:
    name = filename.lower()
    if name.endswith(".xlsx") or name.endswith(".xlsm"):
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        header_row = next(rows_iter, None)
        if not header_row:
            return [], []
        headers = [
            str(c).strip() if c is not None else f"col_{i}" for i, c in enumerate(header_row)
        ]
        rows: list[dict[str, Any]] = []
        for row in rows_iter:
            if row is None or all(c is None or str(c).strip() == "" for c in row):
                continue
            rows.append({headers[i]: row[i] if i < len(row) else None for i in range(len(headers))})
        return headers, rows

    # CSV / TSV
    text = content.decode("utf-8-sig")
    dialect = csv.Sniffer().sniff(text[:4096], delimiters=",\t;")
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = list(reader.fieldnames or [])
    rows = [dict(r) for r in reader]
    return headers, rows


def apply_mapping(row: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    mapped: dict[str, Any] = {}
    for target, source in mapping.items():
        mapped[target] = row.get(source)
    return mapped


def preview_import(content: bytes, filename: str) -> ImportPreviewOut:
    headers, rows = parse_tabular(content, filename)
    mapping = suggest_mapping(headers)
    return ImportPreviewOut(
        headers=headers,
        suggested_mapping=mapping,
        sample_rows=rows[:5],
        row_count=len(rows),
    )


async def run_import(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    content: bytes,
    filename: str,
    mapping: dict[str, str],
    actor_id: UUID,
    default_office_id: UUID | None,
) -> ImportRunOut:
    _headers, rows = parse_tabular(content, filename)
    job = IngestionJob(
        id=uuid4(),
        tenant_id=tenant_id,
        job_type="spreadsheet_import",
        status="running",
        mapping=mapping,
        created_by=actor_id,
    )
    session.add(job)
    await session.flush()

    created = 0
    needs = 0
    skipped = 0
    for row in rows:
        mapped = apply_mapping(row, mapping)
        kind, _id = await create_draft_from_mapped_row(
            session,
            tenant_id=tenant_id,
            mapped=mapped,
            actor_id=actor_id,
            default_office_id=default_office_id,
        )
        if kind == "entry":
            created += 1
        elif kind == "needs_answer":
            needs += 1
        else:
            skipped += 1

    job.status = "completed"
    job.stats = {"created_entries": created, "needs_answer": needs, "skipped": skipped}
    job.finished_at = datetime.now(UTC)
    await write_audit(
        session,
        action="import.run",
        resource_type="ingestion_job",
        resource_id=str(job.id),
        tenant_id=tenant_id,
        actor_user_id=actor_id,
        detail=job.stats,
    )
    return ImportRunOut(job_id=job.id, created_entries=created, needs_answer=needs, skipped=skipped)
