"""Background worker: expiry scan, reminders (Phase 1)."""

from __future__ import annotations

import asyncio
import contextlib
import signal

from amakuru.core.db import dispose_engine, get_session_factory
from amakuru.core.logging import configure_logging, get_logger
from amakuru.core.settings import get_settings
from amakuru.modules.knowledge.expiry import run_expiry_jobs

logger = get_logger("amakuru.worker")
_stop = asyncio.Event()
SCAN_INTERVAL_SECONDS = 3600


def _handle_signal(*_args: object) -> None:
    _stop.set()


async def run_once() -> dict[str, object]:
    settings = get_settings()
    factory = get_session_factory(settings)
    result = await run_expiry_jobs(factory)
    logger.info(
        "expiry_scan_complete",
        expired=result["expired"],
        reminders=result["reminders"],
    )
    return result


async def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    logger.info("worker_started", env=settings.app_env, phase=1)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _handle_signal)

    while not _stop.is_set():
        try:
            await run_once()
        except Exception as exc:  # noqa: BLE001 — keep worker alive
            logger.error("expiry_scan_failed", error=str(exc))
        try:
            await asyncio.wait_for(_stop.wait(), timeout=SCAN_INTERVAL_SECONDS)
        except TimeoutError:
            continue

    await dispose_engine()
    logger.info("worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())
