"""Application lifecycle management."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.settings import get_settings

logger = logging.getLogger(__name__)

_http_client: httpx.AsyncClient | None = None
_health_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown."""
    global _http_client, _health_scheduler

    settings = get_settings()

    # Initialize database (get_db creates connection + schema)
    from app.storage.db import get_db, close_db
    db = await get_db()

    # Run migrations
    from app.storage.migrations import run_migrations
    await run_migrations(db)

    # Create initial client key if none exists
    from app.auth.client_keys import ensure_initial_client_key
    await ensure_initial_client_key()

    # Initialize HTTP client
    _http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(120.0, connect=10.0),
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    )
    app.state.http = _http_client

    # Start health probe scheduler
    try:
        from app.health.scheduler import HealthScheduler
        _health_scheduler = HealthScheduler(_http_client)
        await _health_scheduler.start()
    except Exception:
        logger.warning("Health scheduler failed to start (non-fatal)", exc_info=True)

    logger.info(
        "Gateway started: version=%s, env=%s",
        settings.version,
        settings.deployment_env,
    )

    yield

    # Shutdown
    if _health_scheduler:
        try:
            await _health_scheduler.stop()
        except Exception:
            pass
    if _http_client:
        await _http_client.aclose()
    await close_db()
    logger.info("Gateway stopped")


def get_http_client() -> httpx.AsyncClient:
    """Get the shared HTTP client instance."""
    if _http_client is None:
        raise RuntimeError("HTTP client not initialized")
    return _http_client
