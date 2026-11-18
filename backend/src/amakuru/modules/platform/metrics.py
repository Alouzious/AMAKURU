"""Prometheus-compatible metrics exposition."""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock
from typing import Any

from fastapi import APIRouter, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

router = APIRouter(tags=["metrics"])

_lock = Lock()
_counters: dict[str, float] = defaultdict(float)
_histograms: dict[str, list[float]] = defaultdict(list)


def inc(name: str, value: float = 1.0, **labels: str) -> None:
    key = _label_key(name, labels)
    with _lock:
        _counters[key] += value


def observe(name: str, value: float, **labels: str) -> None:
    key = _label_key(name, labels)
    with _lock:
        bucket = _histograms[key]
        bucket.append(value)
        # Cap memory
        if len(bucket) > 5000:
            del bucket[:2500]


def _label_key(name: str, labels: dict[str, str]) -> str:
    if not labels:
        return name
    parts = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    return f"{name}{{{parts}}}"


def render_prometheus() -> str:
    lines: list[str] = []
    with _lock:
        for key, value in sorted(_counters.items()):
            lines.append(f"{key} {value}")
        for key, values in sorted(_histograms.items()):
            if not values:
                continue
            ordered = sorted(values)
            count = len(ordered)
            total = sum(ordered)
            p50 = ordered[int(0.50 * (count - 1))]
            p95 = ordered[int(0.95 * (count - 1))]
            base = key.split("{", 1)[0]
            labels = ""
            if "{" in key:
                labels = "{" + key.split("{", 1)[1]
            lines.append(f"{base}_count{labels} {count}")
            lines.append(f"{base}_sum{labels} {total}")
            # Extra gauges for ops dashboards
            label_inner = labels[1:-1] if labels.startswith("{") else ""
            sep = "," if label_inner else ""
            lines.append(f'{base}_p50{{{label_inner}{sep}quantile="0.5"}} {p50}')
            lines.append(f'{base}_p95{{{label_inner}{sep}quantile="0.95"}} {p95}')
    return "\n".join(lines) + "\n"


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        started = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - started
        path = request.url.path
        # Low-cardinality path groups
        route = "other"
        if path.startswith("/health") or path.startswith("/ready") or path.startswith("/metrics"):
            route = "ops"
        elif path.startswith("/api/v1/public"):
            route = "public"
        elif path.startswith("/api/v1"):
            route = "api"
        elif path.startswith("/widget"):
            route = "widget"
        status = str(response.status_code)
        inc("amakuru_http_requests_total", method=request.method, route=route, status=status)
        observe("amakuru_http_request_duration_seconds", elapsed, route=route)
        return response


@router.get("/metrics")
async def metrics() -> Response:
    body = render_prometheus()
    return Response(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")


def snapshot() -> dict[str, Any]:
    with _lock:
        return {
            "counters": dict(_counters),
            "histogram_sizes": {k: len(v) for k, v in _histograms.items()},
        }
