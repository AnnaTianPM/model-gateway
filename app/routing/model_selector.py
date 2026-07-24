"""Model selection by task type and difficulty."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def group_by_canonical_model(routes: list[dict]) -> dict[str, list[dict]]:
    """Group eligible routes by canonical model name."""
    groups: dict[str, list[dict]] = {}
    for r in routes:
        name = r.get("canonical_model_name", "")
        if name:
            groups.setdefault(name, []).append(r)
    return groups


def score_models(
    models: dict[str, list[dict]],
    task_type: str,
    static_scores: dict,
    weights: dict | None = None,
) -> list[tuple[str, float]]:
    """Compute weighted task score for each canonical model.

    Returns list of (model_name, score) sorted by score descending.
    """
    from app.models.static_scores import compute_weighted_score

    task_weights = (weights or {}).get(task_type, {})
    scored = []
    for model_name in models:
        score = compute_weighted_score(model_name, task_type, static_scores, task_weights)
        scored.append((model_name, score))

    scored.sort(key=lambda x: -x[1])
    return scored


def select_model_order(
    candidates: list[tuple[str, float]],
    difficulty: str,
    policy: str,
    health_data: dict | None = None,
    quality_floor: dict | None = None,
) -> list[str]:
    """Order models by difficulty strategy.

    Returns list of model names in priority order.
    """
    quality_floor = quality_floor or {}
    health_data = health_data or {}

    if difficulty == "easy":
        floor = quality_floor.get("easy", 75)
        filtered = [(name, score) for name, score in candidates if score >= floor]
        if not filtered:
            filtered = candidates
        # Prefer TTFT (use health data if available)
        filtered.sort(key=lambda x: (-x[1], _get_ttft(x[0], health_data)))
        return [name for name, _ in filtered]

    if difficulty == "medium":
        floor = quality_floor.get("medium", 85)
        filtered = [(name, score) for name, score in candidates if score >= floor]
        if not filtered:
            filtered = candidates
        filtered.sort(key=lambda x: -x[1])
        return [name for name, _ in filtered]

    # hard
    candidates.sort(key=lambda x: -x[1])
    return [name for name, _ in candidates]


def _get_ttft(model_name: str, health_data: dict) -> float:
    """Get best TTFT P95 for a model from health data."""
    best = float("inf")
    for route_id, health in health_data.items():
        if isinstance(health, dict):
            ttft = health.get("ttft_p95_ms")
            if ttft and ttft < best:
                best = ttft
    return best if best != float("inf") else 999999
