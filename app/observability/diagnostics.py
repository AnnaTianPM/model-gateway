"""Diagnostic information for the gateway.

Provides version info and system status for health-check endpoints and
the admin dashboard.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.settings import get_settings

logger = logging.getLogger(__name__)

# Schema version — increment when the database schema changes.
_SCHEMA_VERSION = 1


def get_version_info() -> dict:
    """Return version metadata for the running gateway instance.

    Returns
    -------
    dict
        Keys: ``app_version``, ``git_commit``, ``schema_version``,
        ``deployment_env``.
    """
    settings = get_settings()

    # Try reading VERSION file
    app_version = "dev"
    version_file = Path(settings.app_version_file)
    if version_file.exists():
        try:
            app_version = version_file.read_text().strip()
        except Exception:
            pass
    else:
        # Fallback: look for VERSION next to the project root
        project_version = Path(__file__).resolve().parent.parent.parent / "VERSION"
        if project_version.exists():
            try:
                app_version = project_version.read_text().strip()
            except Exception:
                pass

    return {
        "app_version": app_version,
        "git_commit": settings.git_commit,
        "schema_version": _SCHEMA_VERSION,
        "deployment_env": settings.deployment_env,
    }


async def get_system_status() -> dict:
    """Return the current system status for health/readiness checks.

    Returns
    -------
    dict
        Keys: ``db_ok``, ``scheduler_running``, ``config_loaded``,
        ``healthy_routes``, ``total_routes``, ``circuit_open_count``.
    """
    # --- Database check ---
    db_ok = True
    try:
        from app.storage.db import get_db
        conn = await get_db()
        cursor = await conn.execute("SELECT 1")
        await cursor.fetchone()
    except Exception:
        db_ok = False
        logger.warning("Database health check failed", exc_info=True)

    # --- Config check ---
    config_loaded = True
    try:
        from app.models.static_scores import load_scores
        scores = load_scores()
        config_loaded = bool(scores)
    except Exception:
        config_loaded = False
        logger.warning("Config load check failed", exc_info=True)

    # --- Route health ---
    healthy_routes = 0
    total_routes = 0
    circuit_open_count = 0

    try:
        from app.storage.repositories import RouteHealthRepository, RouteRepository
        all_routes = await RouteRepository.get_all_enabled()
        total_routes = len(all_routes)

        health_data = await RouteHealthRepository.get_all()
        for route_id, rh in health_data.items():
            circuit_state = rh.get("circuit_state", "closed")
            availability = rh.get("availability_5m", 1.0)
            if circuit_state == "open":
                circuit_open_count += 1
            elif availability >= 0.70:
                healthy_routes += 1
    except Exception:
        logger.warning("Failed to query route health", exc_info=True)

    # --- Scheduler status (best-effort) ---
    scheduler_running = False
    # The scheduler is managed by the lifespan; we check if there's a running
    # task by looking for the HealthScheduler instance.
    # This is a placeholder — the actual check is done by the caller
    # who has access to the scheduler instance.
    try:
        import asyncio
        # Check if there are any running tasks that look like the scheduler
        for task in asyncio.all_tasks():
            if "HealthScheduler" in task.get_name():
                scheduler_running = True
                break
    except Exception:
        pass

    return {
        "db_ok": db_ok,
        "scheduler_running": scheduler_running,
        "config_loaded": config_loaded,
        "healthy_routes": healthy_routes,
        "total_routes": total_routes,
        "circuit_open_count": circuit_open_count,
    }
