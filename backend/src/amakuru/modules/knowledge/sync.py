"""Shared connector sync used by API and the background worker."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from amakuru.core.errors import ValidationAppError
from amakuru.core.security import decrypt_secret
from amakuru.core.settings import Settings
from amakuru.modules.knowledge.adapters.rest_json import RestJsonAdapter
from amakuru.modules.knowledge.adapters.spreadsheet import SpreadsheetAdapter
from amakuru.modules.knowledge.adapters.sql_db import SqlDbAdapter
from amakuru.modules.knowledge.adapters.website import WebsiteAdapter
from amakuru.modules.knowledge.models import Connector, IngestionJob
from amakuru.modules.knowledge.service import create_draft_from_mapped_row
from amakuru.modules.platform.audit import write_audit


def build_adapter(adapter_type: str, settings: Settings) -> Any:
    if adapter_type == "spreadsheet":
        return SpreadsheetAdapter()
    if adapter_type == "rest_json":
        return RestJsonAdapter()
    if adapter_type == "sql_db":
        return SqlDbAdapter(allow_private=settings.allow_private_db_connectors)
    if adapter_type == "website":
        return WebsiteAdapter()
    raise ValidationAppError(f"Unknown adapter_type: {adapter_type}")


async def sync_connector(
    session: AsyncSession,
    *,
    connector: Connector,
    settings: Settings,
    actor_id: uuid.UUID | None,
    default_office_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    config: dict[str, Any] = {}
    if connector.config_encrypted:
        config = json.loads(decrypt_secret(settings, connector.config_encrypted))

    adapter = build_adapter(connector.adapter_type, settings)
    rows = await adapter.fetch_rows(config)

    job = IngestionJob(
        id=uuid.uuid4(),
        tenant_id=connector.tenant_id,
        job_type=f"connector:{connector.adapter_type}",
        status="running",
        mapping=connector.field_mapping,
        created_by=actor_id,
    )
    session.add(job)
    await session.flush()

    drafts = 0
    needs = 0
    errors = 0
    for row in rows:
        try:
            mapped = adapter.map_row(
                row, {str(k): str(v) for k, v in connector.field_mapping.items()}
            )
            if actor_id is None:
                errors += 1
                continue
            kind, _id = await create_draft_from_mapped_row(
                session,
                tenant_id=connector.tenant_id,
                mapped=dict(mapped),
                actor_id=actor_id,
                default_office_id=default_office_id,
            )
            if kind == "entry":
                drafts += 1
            elif kind == "needs_answer":
                needs += 1
        except Exception:  # noqa: BLE001 — continue batch
            errors += 1

    stats = {
        "drafts_created": drafts,
        "needs_answer": needs,
        "rows": len(rows),
        "errors": errors,
    }
    job.status = "completed"
    job.stats = stats
    job.finished_at = datetime.now(UTC)
    connector.last_synced_at = datetime.now(UTC)
    await write_audit(
        session,
        action="connector.sync",
        resource_type="connector",
        resource_id=str(connector.id),
        tenant_id=connector.tenant_id,
        actor_user_id=actor_id,
        detail=stats,
    )
    return {"job_id": job.id, **stats}
