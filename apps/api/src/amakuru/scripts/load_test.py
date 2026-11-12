"""Lightweight concurrent load test for Phase 6.

Reports latency percentiles for /health and public chat bootstrap + message.
Does not fabricate numbers — figures come only from this run.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from typing import Any

import httpx

from amakuru.scripts.seed import DEMO_WIDGET_KEY


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((p / 100.0) * (len(ordered) - 1)))))
    return ordered[idx]


async def _timed(client: httpx.AsyncClient, method: str, url: str, **kwargs: Any) -> float:
    started = time.perf_counter()
    resp = await client.request(method, url, **kwargs)
    elapsed = (time.perf_counter() - started) * 1000
    resp.raise_for_status()
    return elapsed


async def run_load(
    *,
    base: str,
    concurrency: int,
    requests: int,
    widget_key: str,
) -> dict[str, Any]:
    health_ms: list[float] = []
    boot_ms: list[float] = []
    msg_ms: list[float] = []
    errors = 0
    sem = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(base_url=base, timeout=30.0) as client:

        async def one(i: int) -> None:
            nonlocal errors
            async with sem:
                try:
                    health_ms.append(await _timed(client, "GET", "/health"))
                    boot_ms.append(
                        await _timed(
                            client,
                            "GET",
                            "/api/v1/public/chat/bootstrap",
                            headers={"X-Amakuru-Key": widget_key},
                        )
                    )
                    # Alternate greetings / known demo question to exercise cache + retrieval
                    q = "hello" if i % 3 == 0 else "What is this demo chatbot for?"
                    msg_ms.append(
                        await _timed(
                            client,
                            "POST",
                            "/api/v1/public/chat/message",
                            headers={"X-Amakuru-Key": widget_key},
                            json={"question": q, "language": "en"},
                        )
                    )
                except Exception:
                    errors += 1

        await asyncio.gather(*(one(i) for i in range(requests)))

    def summary(name: str, values: list[float]) -> dict[str, float]:
        return {
            "n": float(len(values)),
            "mean_ms": statistics.fmean(values) if values else 0.0,
            "p50_ms": _pct(values, 50),
            "p95_ms": _pct(values, 95),
            "max_ms": max(values) if values else 0.0,
        }

    return {
        "base": base,
        "concurrency": concurrency,
        "requests": requests,
        "errors": errors,
        "health": summary("health", health_ms),
        "bootstrap": summary("bootstrap", boot_ms),
        "message": summary("message", msg_ms),
    }


def format_report(payload: dict[str, Any]) -> str:
    lines = [
        "Amakuru load test report",
        "------------------------",
        f"base:         {payload['base']}",
        f"concurrency:  {payload['concurrency']}",
        f"iterations:   {payload['requests']}",
        f"errors:       {payload['errors']}",
    ]
    for key in ("health", "bootstrap", "message"):
        s = payload[key]
        lines.append(
            f"{key:12} n={int(s['n'])} mean={s['mean_ms']:.1f}ms "
            f"p50={s['p50_ms']:.1f}ms p95={s['p95_ms']:.1f}ms max={s['max_ms']:.1f}ms"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--requests", type=int, default=40)
    parser.add_argument("--widget-key", default=DEMO_WIDGET_KEY)
    args = parser.parse_args()
    payload = asyncio.run(
        run_load(
            base=args.base.rstrip("/"),
            concurrency=args.concurrency,
            requests=args.requests,
            widget_key=args.widget_key,
        )
    )
    print(format_report(payload))
    if payload["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
