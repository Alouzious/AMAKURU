"""Background worker: expiry, connector sync, live-search promotion."""

from __future__ import annotations

import asyncio
import contextlib
import signal
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select

from amakuru.core.db import dispose_engine, get_session_factory, set_tenant
from amakuru.core.logging import configure_logging, get_logger
from amakuru.core.settings import get_settings
from amakuru.modules.identity.models import Membership, User
from amakuru.modules.knowledge.expiry import run_expiry_jobs
from amakuru.modules.knowledge.models import Connector
from amakuru.modules.knowledge.search_intel import promote_hot_searches_to_drafts
from amakuru.modules.knowledge.sync import sync_connector
from amakuru.modules.tenancy.models import Tenant

logger = get_logger("amakuru.worker")
_stop = asyncio.Event()


def _handle_signal(*_args: object) -> None:
    _stop.set()


async def _actor_for_tenant(session: Any, tenant_id: UUID) -> UUID | None:
    result = await session.execute(
        select(Membership.user_id)
        .where(Membership.tenant_id == tenant_id, Membership.role == "tenant_admin")
        .limit(1)
    )
    uid = result.scalar_one_or_none()
    if uid:
        return uid
    result = await session.execute(
        select(Membership.user_id).where(Membership.tenant_id == tenant_id).limit(1)
    )
    return result.scalar_one_or_none()


async def run_connector_syncs() -> dict[str, object]:
    settings = get_settings()
    factory = get_session_factory(settings)
    synced = 0
    errors = 0
    async with factory() as session:
        result = await session.execute(
            select(Connector).where(Connector.is_active.is_(True))
        )
        connectors = list(result.scalars().all())
        for connector in connectors:
            # Simple interval: if schedule_cron empty, use global interval since last sync
            due = True
            if connector.last_synced_at is not None:
                age = datetime.now(UTC) - connector.last_synced_at
                due = age >= timedelta(seconds=settings.connector_sync_interval_seconds)
            if not due:
                continue
            try:
                async with session.begin():
                    await set_tenant(session, connector.tenant_id)
                    actor = await _actor_for_tenant(session, connector.tenant_id)
                    if actor is None:
                        # Fall back to any platform admin
                        admin = await session.execute(
                            select(User.id).where(User.is_platform_admin.is_(True)).limit(1)
                        )
                        actor = admin.scalar_one_or_none()
                    if actor is None:
                        logger.warning(
                            "connector_sync_skipped_no_actor", connector_id=str(connector.id)
                        )
                        continue
                    await sync_connector(
                        session,
                        connector=connector,
                        settings=settings,
                        actor_id=actor,
                    )
                    synced += 1
            except Exception as exc:  # noqa: BLE001
                errors += 1
                logger.error(
                    "connector_sync_failed",
                    connector_id=str(connector.id),
                    error=str(exc),
                )
    return {"synced": synced, "errors": errors}


async def run_search_promotion() -> dict[str, object]:
    settings = get_settings()
    factory = get_session_factory(settings)
    total = 0
    async with factory() as session:
        tenants = (
            await session.execute(select(Tenant.id).where(Tenant.status == "active"))
        ).scalars().all()
        for tenant_id in tenants:
            try:
                async with session.begin():
                    await set_tenant(session, tenant_id)
                    actor = await _actor_for_tenant(session, tenant_id)
                    if actor is None:
                        continue
                    out = await promote_hot_searches_to_drafts(
                        session,
                        tenant_id=tenant_id,
                        actor_id=actor,
                        min_count=settings.search_promote_min_count,
                    )
                    total += int(out.get("created") or 0)
            except Exception as exc:  # noqa: BLE001
                logger.error("search_promote_failed", tenant_id=str(tenant_id), error=str(exc))
    return {"promoted": total}


async def run_once() -> dict[str, object]:
    settings = get_settings()
    factory = get_session_factory(settings)
    expiry = await run_expiry_jobs(factory)
    connectors = await run_connector_syncs()
    searches = await run_search_promotion()
    logger.info(
        "worker_cycle_complete",
        expired=expiry.get("expired"),
        reminders=expiry.get("reminders"),
        connectors_synced=connectors.get("synced"),
        searches_promoted=searches.get("promoted"),
    )
    return {"expiry": expiry, "connectors": connectors, "searches": searches}


async def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    interval = settings.worker_scan_interval_seconds
    logger.info("worker_started", env=settings.app_env, interval=interval)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _handle_signal)

    while not _stop.is_set():
        try:
            await run_once()
        except Exception as exc:  # noqa: BLE001 — keep worker alive
            logger.error("worker_cycle_failed", error=str(exc))
        try:
            await asyncio.wait_for(_stop.wait(), timeout=interval)
        except TimeoutError:
            continue

    await dispose_engine()
    logger.info("worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())
