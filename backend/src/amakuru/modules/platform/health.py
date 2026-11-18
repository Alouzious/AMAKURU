"""Health and readiness endpoints."""

from __future__ import annotations

from typing import Any

import redis.asyncio as redis
from fastapi import APIRouter, Response
from sqlalchemy import text

from amakuru.core.db import get_engine
from amakuru.core.settings import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": get_settings().app_name}


@router.get("/ready")
async def ready(response: Response) -> dict[str, Any]:
    settings = get_settings()
    checks: dict[str, Any] = {"database": False, "redis": False}
    try:
        engine = get_engine(settings)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as exc:  # noqa: BLE001 — readiness must report failure reason
        checks["database_error"] = str(exc)

    try:
        client = redis.from_url(settings.redis_url)
        pong = await client.ping()
        checks["redis"] = bool(pong)
        close = getattr(client, "aclose", None) or client.close
        await close()
    except Exception as exc:  # noqa: BLE001
        checks["redis_error"] = str(exc)

    ok = bool(checks["database"] and checks["redis"])
    if not ok:
        response.status_code = 503
    return {"status": "ready" if ok else "not_ready", "checks": checks}
