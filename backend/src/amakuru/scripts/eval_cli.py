"""CLI entry for `make eval`."""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select

from amakuru.core.db import dispose_engine, get_session_factory, set_tenant
from amakuru.core.logging import configure_logging
from amakuru.core.settings import get_settings
from amakuru.modules.evaluation.harness import format_report, run_eval
from amakuru.modules.retrieval.indexing import index_tenant
from amakuru.modules.retrieval.providers.embeddings import build_embedding_provider
from amakuru.modules.retrieval.vector_store import PgVectorStore
from amakuru.modules.tenancy.models import Tenant


async def _async_main(tenant_slug: str) -> int:
    settings = get_settings()
    configure_logging(settings)
    factory = get_session_factory(settings)
    async with factory() as session, session.begin():
        result = await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))
        tenant = result.scalar_one_or_none()
        if tenant is None:
            print(f"FAIL tenant slug not found: {tenant_slug}", file=sys.stderr)
            return 1
        await set_tenant(session, tenant.id)
        embedder = build_embedding_provider(settings)
        store = PgVectorStore()
        index_stats = await index_tenant(
            session,
            tenant_id=tenant.id,
            embedder=embedder,
            store=store,
            settings=settings,
        )
        print(f"Indexed: {index_stats}")
        payload = await run_eval(
            session, tenant_id=tenant.id, settings=settings, trigger="make_eval"
        )
        print(format_report(payload))
        code = 0 if payload["passed"] else 2
    await dispose_engine()
    return code


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Amakuru retrieval evaluation")
    parser.add_argument("--tenant", default="demo-university")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_async_main(args.tenant)))


if __name__ == "__main__":
    main()
