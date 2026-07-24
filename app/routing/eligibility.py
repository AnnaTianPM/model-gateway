"""Hard filtering of routes based on requirements and health."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def filter_routes(
    routes: list[dict],
    required_capabilities: set[str],
    minimum_context_length: int,
    client_permissions: list[str] | None = None,
    health_data: dict | None = None,
    min_samples: int = 3,
    min_reliability_lcb: float = 0.90,
    min_availability_5m: float = 0.70,
) -> tuple[list[dict], list[dict]]:
    """Filter routes by capabilities, context, health, and permissions.

    Returns (eligible_routes, warming_routes).
    Warming routes have insufficient samples but pass capability checks.
    """
    health_data = health_data or {}

    eligible = []
    warming = []

    for route in routes:
        # Capability check
        if "vision" in required_capabilities and not route.get("supports_vision"):
            continue
        if "tools" in required_capabilities and not route.get("supports_tools"):
            continue
        if "json" in required_capabilities and not route.get("supports_json"):
            continue
        if "stream" in required_capabilities and not route.get("supports_stream", True):
            continue

        # Context length check
        ctx = route.get("context_length", 32768)
        if ctx and ctx < minimum_context_length:
            continue

        # Client permissions check
        if client_permissions:
            canonical = route.get("canonical_model_name", "")
            if canonical and canonical not in client_permissions:
                continue

        # Health check
        route_health = health_data.get(route["id"], {})
        circuit_state = route_health.get("circuit_state", "closed")
        if circuit_state == "open":
            continue

        samples = route_health.get("successes_5m", 0) + route_health.get("failures_5m", 0)
        if samples < min_samples:
            # Warming route — can be used as fallback
            warming.append(route)
            continue

        availability = route_health.get("availability_5m", 1.0)
        reliability = route_health.get("reliability_lcb", 1.0)

        if availability < min_availability_5m:
            continue
        if reliability < min_reliability_lcb:
            continue

        eligible.append(route)

    return eligible, warming
