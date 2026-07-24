"""Fallback chain builder."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def build_fallback_chain(
    eligible_routes: list[dict],
    selected_models: list[str],
    route_health: dict | None = None,
    max_attempts: int = 4,
) -> list[dict]:
    """Build ordered fallback list of routes.

    Order:
    1. Same model providers first (sorted by reliability/TTFT)
    2. Then next model providers
    3. Max max_attempts total
    """
    from app.routing.route_selector import sort_routes_for_model

    # Group routes by canonical model
    by_model: dict[str, list[dict]] = {}
    for r in eligible_routes:
        name = r.get("canonical_model_name", "")
        if name:
            by_model.setdefault(name, []).append(r)

    chain = []
    for model_name in selected_models:
        model_routes = by_model.get(model_name, [])
        sorted_routes = sort_routes_for_model(model_routes, route_health or {})
        chain.extend(sorted_routes)
        if len(chain) >= max_attempts:
            break

    return chain[:max_attempts]
