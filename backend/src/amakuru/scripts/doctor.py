"""Validate configuration and connectivity. Plain messages only."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import redis.asyncio as redis
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from amakuru.core.settings import Settings, clear_settings_cache


def _ok(name: str, detail: str = "") -> None:
    suffix = f" — {detail}" if detail else ""
    print(f"OK   {name}{suffix}")


def _fail(name: str, detail: str) -> None:
    print(f"FAIL {name} — {detail}")


def _warn(name: str, detail: str) -> None:
    print(f"WARN {name} — {detail}")


async def _check_db(settings: Settings) -> bool:
    try:
        engine = create_async_engine(settings.database_url)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            ext = await conn.execute(
                text("SELECT extname FROM pg_extension WHERE extname IN ('vector', 'pgcrypto')")
            )
            names = {row[0] for row in ext.fetchall()}
        await engine.dispose()
        missing = {"vector", "pgcrypto"} - names
        if missing:
            _warn("database", f"connected but missing extensions: {', '.join(sorted(missing))}")
        else:
            host = f"{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
            _ok("database", host)
        return True
    except Exception as exc:  # noqa: BLE001
        _fail("database", str(exc))
        return False


async def _check_redis(settings: Settings) -> bool:
    try:
        client = redis.from_url(settings.redis_url)
        await client.ping()
        await client.close()
        _ok("redis", settings.redis_url)
        return True
    except Exception as exc:  # noqa: BLE001
        _fail("redis", str(exc))
        return False


async def _check_llm(settings: Settings) -> None:
    if not settings.llm_api_key or settings.llm_api_key.startswith("not-required"):
        _warn("llm", "LLM_API_KEY not set (OK for Phase 0 foundation)")
        return
    if not settings.allow_external_ai_calls:
        _ok("llm", "ALLOW_EXTERNAL_AI_CALLS=false (sovereign mode)")
        return
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.llm_base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            )
        if resp.status_code < 500:
            _ok("llm", f"{settings.llm_provider} reachable (HTTP {resp.status_code})")
        else:
            _warn("llm", f"provider returned HTTP {resp.status_code}")
    except Exception as exc:  # noqa: BLE001
        _warn("llm", f"could not reach provider: {exc}")


def _check_settings() -> Settings | None:
    clear_settings_cache()
    try:
        settings = Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        _fail("settings", "validation failed:")
        for err in exc.errors():
            loc = ".".join(str(x) for x in err["loc"])
            print(f"       {loc}: {err['msg']}")
        return None

    required: list[tuple[str, Any]] = [
        ("SECRET_KEY", settings.secret_key),
        ("ENCRYPTION_KEY", settings.encryption_key),
        ("BOOTSTRAP_ADMIN_EMAIL", settings.bootstrap_admin_email),
        ("BOOTSTRAP_ADMIN_PASSWORD", settings.bootstrap_admin_password),
    ]
    missing = [name for name, value in required if not value]
    if missing:
        _fail("settings", f"missing required values: {', '.join(missing)}")
        return None

    if len(settings.bootstrap_admin_password) < 12:
        _fail("settings", "BOOTSTRAP_ADMIN_PASSWORD must be at least 12 characters")
        return None

    _ok("settings", f"env={settings.app_env}")
    return settings


async def _async_main() -> int:
    print("Amakuru doctor")
    print("--------------")
    settings = _check_settings()
    if settings is None:
        return 1

    db_ok = await _check_db(settings)
    redis_ok = await _check_redis(settings)
    await _check_llm(settings)

    if settings.seed_demo_data:
        _ok("seed", "SEED_DEMO_DATA=true (demo tenant will be labelled as demonstration)")
    else:
        _ok("seed", "SEED_DEMO_DATA=false")

    print("--------------")
    if db_ok and redis_ok:
        print("Doctor finished: ready for Phase 0.")
        return 0
    print("Doctor finished: fix FAIL items above.")
    return 1


def main() -> None:
    raise SystemExit(asyncio.run(_async_main()))


if __name__ == "__main__":
    main()
