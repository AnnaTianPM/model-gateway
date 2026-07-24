"""Background health-probe scheduler.

Runs active probes against all enabled routes at a configurable interval.
When any route is degraded (open circuit or low availability), the interval
shortens to ``degraded_probe_interval_seconds`` for faster recovery detection.

Special probes (tools, json, vision) run at a lower frequency (default 6 h)
to minimise token consumption.
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from app.health.probes import (
    json_probe_payload,
    probe_route,
    tools_probe_payload,
    vision_probe_payload,
)
from app.health.metrics import update_route_health
from app.storage.repositories import (
    HealthEventRepository,
    RouteHealthRepository,
    RouteRepository,
)

logger = logging.getLogger(__name__)

# Default configuration (mirror config/routing_rules.yaml).
_DEFAULT_PROBE_INTERVAL = 300       # 5 minutes
_DEFAULT_DEGRADED_INTERVAL = 60     # 1 minute
_DEFAULT_PROBE_TIMEOUT = 30.0
_DEFAULT_PROBE_CONCURRENCY = 10
_SPECIAL_PROBE_INTERVAL = 21600     # 6 hours


class HealthScheduler:
    """Async background task that probes routes and updates health state.

    Usage::

        scheduler = HealthScheduler(http_client)
        await scheduler.start()
        ...
        await scheduler.stop()
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        probe_interval: int = _DEFAULT_PROBE_INTERVAL,
        degraded_interval: int = _DEFAULT_DEGRADED_INTERVAL,
        probe_timeout: float = _DEFAULT_PROBE_TIMEOUT,
        concurrency: int = _DEFAULT_PROBE_CONCURRENCY,
    ) -> None:
        self._http_client = http_client
        self._probe_interval = probe_interval
        self._degraded_interval = degraded_interval
        self._probe_timeout = probe_timeout
        self._concurrency = concurrency
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_special_probe: float = 0.0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background probe loop."""
        if self._task is not None and not self._task.done():
            logger.warning("HealthScheduler already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("HealthScheduler started (interval=%ds)", self._probe_interval)

    async def stop(self) -> None:
        """Stop the background probe loop gracefully."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("HealthScheduler stopped")

    @property
    def is_running(self) -> bool:
        """Whether the scheduler is currently active."""
        return self._running and self._task is not None and not self._task.done()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _run_loop(self) -> None:
        """Main probe loop."""
        while self._running:
            try:
                await self._probe_all_routes()

                # Check if we should run special probes
                now = time.time()
                if now - self._last_special_probe >= _SPECIAL_PROBE_INTERVAL:
                    await self._run_special_probes()
                    self._last_special_probe = now

            except Exception:
                logger.exception("HealthScheduler loop error")

            # Determine sleep interval
            interval = self._probe_interval
            if await self._is_degraded():
                interval = self._degraded_interval
                logger.info("Degraded mode: using %ds probe interval", interval)

            # Sleep in small increments for faster shutdown
            slept = 0
            while self._running and slept < interval:
                await asyncio.sleep(min(5, interval - slept))
                slept += 5

    async def _is_degraded(self) -> bool:
        """Check if any route is in a degraded state (open circuit / low availability)."""
        try:
            health_data = await RouteHealthRepository.get_all()
            for route_id, rh in health_data.items():
                if rh.get("circuit_state") == "open":
                    return True
                if rh.get("availability_5m", 1.0) < 0.70:
                    return True
        except Exception:
            logger.debug("Failed to check degraded state", exc_info=True)
        return False

    async def _probe_all_routes(self) -> None:
        """Probe all enabled routes with basic probes."""
        try:
            routes = await RouteRepository.get_all_enabled()
        except Exception:
            logger.exception("Failed to load routes for probing")
            return

        if not routes:
            logger.debug("No enabled routes to probe")
            return

        sem = asyncio.Semaphore(self._concurrency)

        async def _probe_one(route: dict) -> None:
            async with sem:
                event = await probe_route(
                    route,
                    self._http_client,
                    payload=None,  # basic probe
                    source="probe",
                    timeout=self._probe_timeout,
                )
                await self._record_and_aggregate(event, route)

        await asyncio.gather(
            *[_probe_one(r) for r in routes],
            return_exceptions=True,
        )

        logger.info("Probe cycle complete: %d routes checked", len(routes))

    async def _run_special_probes(self) -> None:
        """Run capability-specific probes (tools, json, vision)."""
        try:
            routes = await RouteRepository.get_all_enabled()
        except Exception:
            logger.exception("Failed to load routes for special probes")
            return

        sem = asyncio.Semaphore(self._concurrency)

        async def _probe_special(route: dict, payload: dict, cap_name: str) -> None:
            # Only probe routes that support the capability
            if cap_name == "tools" and not route.get("supports_tools"):
                return
            if cap_name == "json" and not route.get("supports_json"):
                return
            if cap_name == "vision" and not route.get("supports_vision"):
                return

            async with sem:
                event = await probe_route(
                    route,
                    self._http_client,
                    payload=payload,
                    source="probe_special",
                    timeout=self._probe_timeout,
                )
                await self._record_and_aggregate(event, route)

        tasks = []
        for route in routes:
            tasks.append(_probe_special(route, tools_probe_payload(), "tools"))
            tasks.append(_probe_special(route, json_probe_payload(), "json"))
            tasks.append(_probe_special(route, vision_probe_payload(), "vision"))

        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Special probe cycle complete")

    async def _record_and_aggregate(self, event: dict, route: dict) -> None:
        """Record a health event and update the route's aggregate health."""
        route_id = event.get("route_id", 0)
        if not route_id:
            return

        # 1. Insert the health event
        try:
            await HealthEventRepository.insert(event)
        except Exception:
            logger.exception("Failed to insert health event for route %d", route_id)
            return

        # 2. Fetch recent events and re-aggregate
        try:
            # Fetch events from the last 24 hours for aggregation
            since = time.time() - 86400
            events = await HealthEventRepository.get_by_route(route_id, since)
            await update_route_health(route_id, events)
        except Exception:
            logger.exception("Failed to update route_health for route %d", route_id)
