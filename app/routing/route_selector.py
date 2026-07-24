"""Provider route selection within a model."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def sort_routes_for_model(routes: list[dict], health_data: dict) -> list[dict]:
    """Sort routes for a single model by reliability, TTFT, and quota.

    Sort order:
    1. reliability_lcb descending
    2. ttft_p95 ascending
    3. quota_remaining descending
    4. 429 penalty (routes with recent 429s are deprioritized)
    """
    def sort_key(route: dict) -> tuple:
        route_id = route.get("id", 0)
        health = health_data.get(route_id, {})

        reliability = health.get("reliability_lcb", 1.0)
        ttft = health.get("ttft_p95_ms") or 999999
        quota = route.get("quota_remaining") or 0
        has_429 = 1 if health.get("cooldown_reason") == "rate_limited" else 0

        return (-reliability, ttft, -quota, has_429)

    return sorted(routes, key=sort_key)
