"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from amakuru import __version__
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
from amakuru.modules.analytics.router import router as analytics_router
from amakuru.modules.billing.router import external_router as billing_external_router
from amakuru.modules.billing.router import router as billing_router
from amakuru.modules.channels.router import router as channels_public_router
from amakuru.modules.channels.whatsapp import router as whatsapp_router
from amakuru.modules.identity.router import router as identity_router
from amakuru.modules.knowledge.router import router as knowledge_router
from amakuru.modules.platform.health import router as health_router
from amakuru.modules.platform.metrics import MetricsMiddleware
from amakuru.modules.platform.metrics import router as metrics_router
from amakuru.modules.retrieval.router import router as retrieval_router
from amakuru.modules.tenancy.router import router as tenancy_router

logger = get_logger("amakuru.main")

# main.py → amakuru → src → api → apps
WIDGET_DIST = Path(__file__).resolve().parents[3] / "widget" / "dist"


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
        lifespan=lifespan,
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url=None,
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
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        # Allow widget embedding on approved host pages
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

    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(identity_router, prefix="/api/v1")
    app.include_router(tenancy_router, prefix="/api/v1")
    app.include_router(knowledge_router, prefix="/api/v1")
    app.include_router(retrieval_router, prefix="/api/v1")
    app.include_router(analytics_router, prefix="/api/v1")
    app.include_router(billing_router, prefix="/api/v1")
    app.include_router(billing_external_router, prefix="/api/v1")
    app.include_router(channels_public_router, prefix="/api/v1")
    app.include_router(whatsapp_router, prefix="/api/v1")

    @app.get("/")
    async def root() -> dict[str, Any]:
        return {"name": settings.app_name, "version": __version__, "phase": 7}

    @app.get("/widget/demo", response_class=HTMLResponse)
    async def widget_demo() -> str:
        script_src = "/widget/amakuru-widget.js"
        api = settings.api_base_url
        # noqa below: demo HTML template kept compact on purpose
        return (
            "<!doctype html><html lang='en'><head>"
            "<meta charset='utf-8'/>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'/>"
            "<title>Amakuru widget demo</title>"
            "<style>body{font-family:Georgia,serif;margin:2rem;background:#faf7f2;"
            "color:#1c1917}a{color:#0f766e}</style></head><body>"
            "<h1>Amakuru demo host page</h1>"
            "<p>DEMONSTRATION ONLY — open the chat button in the corner.</p>"
            "<p>API docs: <a href='/docs'>/docs</a></p>"
            "<script>window.AmakuruConfig={"
            f"apiBase:'{api}',"
            "key:'ak_live_demo_university_key_change_me',language:'en'};"
            "</script>"
            f"<script src='{script_src}' defer></script>"
            "</body></html>"
        )

    if WIDGET_DIST.is_dir():
        app.mount("/widget", StaticFiles(directory=str(WIDGET_DIST), html=False), name="widget")

    return app


app = create_app()
