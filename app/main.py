"""FastAPI application entry point."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.lifespan import lifespan
from app.logging_config import setup_logging
from app.settings import get_settings

# Set up logging before anything else
setup_logging()

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Model Gateway",
    description="LAN AI API Gateway with smart routing and multi-provider failover",
    version="0.1.0",
    lifespan=lifespan,
)

# Templates and static files
_templates_dir = Path(__file__).resolve().parent / "dashboard" / "templates"
_static_dir = Path(__file__).resolve().parent / "dashboard" / "static"

if _templates_dir.exists():
    templates = Jinja2Templates(directory=str(_templates_dir))
    templates.env.auto_reload = True
else:
    templates = None

if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


# --- Middleware ---
@app.middleware("http")
async def no_cache_middleware(request, call_next):
    """Add no-cache headers for pages and API responses."""
    resp = await call_next(request)
    if request.url.path in ("/",) or request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp


# --- Health endpoints (no auth) ---
@app.get("/health/live")
async def health_live():
    """Liveness probe - process is alive."""
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready():
    """Readiness probe - check database, scheduler, config."""
    from app.observability.diagnostics import get_system_status
    status = get_system_status()
    code = 200 if status.get("db_ok") else 503
    return JSONResponse(content=status, status_code=code)


# --- Version endpoint ---
@app.get("/api/admin/version")
async def version_info():
    """Return version information."""
    from app.observability.diagnostics import get_version_info
    return get_version_info()


# --- Register API routers ---
def _register_routers():
    """Import and include API routers."""
    try:
        from app.api.openai import router as openai_router
        app.include_router(openai_router, prefix="/v1")
    except ImportError:
        logger.debug("OpenAI router not yet available")

    try:
        from app.api.admin_providers import router as providers_router
        app.include_router(providers_router, prefix="/api/admin")
    except ImportError:
        logger.debug("Admin providers router not yet available")

    try:
        from app.api.admin_models import router as models_router
        app.include_router(models_router, prefix="/api/admin")
    except ImportError:
        logger.debug("Admin models router not yet available")

    try:
        from app.api.admin_health import router as health_router
        app.include_router(health_router, prefix="/api/admin")
    except ImportError:
        logger.debug("Admin health router not yet available")

    try:
        from app.api.admin_routing import router as routing_router
        app.include_router(routing_router, prefix="/api/admin")
    except ImportError:
        logger.debug("Admin routing router not yet available")

    try:
        from app.api.admin_clients import router as clients_router
        app.include_router(clients_router, prefix="/api/admin")
    except ImportError:
        logger.debug("Admin clients router not yet available")

    try:
        from app.api.admin_usage import router as usage_router
        app.include_router(usage_router, prefix="/api/admin")
    except ImportError:
        logger.debug("Admin usage router not yet available")


_register_routers()


# --- Dashboard route ---
@app.get("/")
async def dashboard(request: Request):
    """Serve the dashboard page."""
    if templates:
        from app.settings import get_settings
        settings = get_settings()
        return templates.TemplateResponse(
            request,
            "index.html",
            {"app_version": settings.version},
        )
    return JSONResponse(
        content={"message": "Dashboard templates not found. API is available at /v1/ and /api/admin/."}
    )
