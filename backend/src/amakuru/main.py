"""FastAPI REST application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from amakuru import __version__
from amakuru.api import api_v1
from amakuru.core.db import dispose_engine, get_engine
from amakuru.core.errors import (
    AmakuruError,
    AuthError,
    ForbiddenError,
    NotFoundError,
    QuotaExceededError,
)
from amakuru.core.logging import configure_logging, get_logger
from amakuru.core.settings import get_settings
from amakuru.modules.platform.health import router as health_router
from amakuru.modules.platform.metrics import MetricsMiddleware
from amakuru.modules.platform.metrics import router as metrics_router

logger = get_logger("amakuru.main")

# main.py → amakuru → src → backend → AMAKURU
WIDGET_DIST = Path(__file__).resolve().parents[3] / "frontend" / "widget" / "dist"


@asynccontextmanager
async def lifespan(_app: FastAPI):  # type: ignore[no-untyped-def]
    settings = get_settings()
    configure_logging(settings)
    get_engine(settings)
    logger.info("api_started", version=__version__, env=settings.app_env)
    yield
    await dispose_engine()
    logger.info("api_stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="Amakuru REST API: verified FAQ assistant for organizations.",
        lifespan=lifespan,
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url="/redoc" if settings.app_env != "production" else None,
        openapi_url="/openapi.json" if settings.app_env != "production" else None,
    )

    origins = list(settings.cors_origins)
    for extra in ("http://localhost:5173", "http://127.0.0.1:5173", "null"):
        if extra not in origins:
            origins.append(extra)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins if "*" not in origins else ["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    app.add_middleware(MetricsMiddleware)

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        import uuid

        import structlog

        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        # script-src 'self' allows /widget/amakuru-widget.js; connect-src for chat API.
        # Avoid blocking the demo page: config is JSON, not inline JS.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "connect-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        if not request.url.path.startswith("/widget"):
            response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.exception_handler(AmakuruError)
    async def amakuru_error_handler(_request: Request, exc: AmakuruError) -> JSONResponse:
        status = 400
        if isinstance(exc, AuthError):
            status = 401
        elif isinstance(exc, ForbiddenError):
            status = 403
        elif isinstance(exc, NotFoundError):
            status = 404
        elif isinstance(exc, QuotaExceededError):
            status = 429
        return JSONResponse(status_code=status, content={"error": exc.code, "message": exc.message})

    # Ops
    app.include_router(health_router)
    app.include_router(metrics_router)

    # REST API v1
    app.include_router(api_v1)

    @app.get("/", tags=["root"])
    async def root() -> dict[str, Any]:
        return {
            "name": settings.app_name,
            "version": __version__,
            "docs": "/docs",
            "api": "/api/v1",
        }

    @app.get("/widget/demo", response_class=HTMLResponse, include_in_schema=False)
    async def widget_demo() -> str:
        # Config is JSON (not executable JS) so CSP script-src 'self' still works.
        return (
            "<!doctype html><html lang='en'><head>"
            "<meta charset='utf-8'/>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'/>"
            "<title>Amakuru chat demo</title>"
            "<style>"
            "body{font-family:Georgia,serif;margin:2rem;background:#faf7f2;color:#1c1917}"
            "a{color:#0f766e}"
            ".hint{margin-top:1.5rem;padding:1rem 1.25rem;border:1px solid #d6d3d1;"
            "background:#fff;max-width:28rem}"
            ".hint strong{display:block;margin-bottom:.35rem}"
            "</style></head><body>"
            "<h1>Amakuru chat demo</h1>"
            "<div class='hint'>"
            "<strong>Look for the green “Ask Amakuru” button</strong>"
            "It floats in the bottom-right corner of this page. "
            "Click it, then type a question or tap Fees / Admissions."
            "</div>"
            "<p style='margin-top:1.5rem'>"
            "Staff dashboard: <a href='http://localhost:3000'>localhost:3000</a>"
            " · API docs: <a href='/docs'>/docs</a>"
            "</p>"
            '<script id="amakuru-config" type="application/json">'
            '{"apiBase":"","key":"ak_live_demo_university_key_change_me","language":"en"}'
            "</script>"
            '<script src="/widget/amakuru-widget.js" defer'
            ' data-amakuru-key="ak_live_demo_university_key_change_me"'
            ' data-amakuru-api=""'
            ' data-amakuru-lang="en"></script>'
            "</body></html>"
        )

    if WIDGET_DIST.is_dir():
        app.mount("/widget", StaticFiles(directory=str(WIDGET_DIST), html=False), name="widget")

    return app


app = create_app()
