"""Route service orchestrator.

Ties together the entire routing pipeline:

    extract_features → classify → filter → score → select → sort → fallback

Handles logical-model resolution and explicit model requests.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.models.canonical import normalize_model_name
from app.models.static_scores import load_scores, compute_weighted_score, get_context_length
from app.routing.decision import RouteDecision, record_decision
from app.routing.eligibility import filter_routes
from app.routing.fallback import build_fallback_chain
from app.routing.model_selector import group_by_canonical_model, score_models, select_model_order
from app.routing.request_features import RequestFeatures, extract_features
from app.routing.rule_classifier import RequestClassification, classify
from app.routing.route_selector import sort_routes_for_model
from app.settings import get_settings
from app.storage.repositories import RouteHealthRepository, RouteRepository

logger = logging.getLogger(__name__)

_LOGICAL_TASK_OVERRIDE: dict[str, str] = {
    "auto-coding": "coding",
    "auto-reasoning": "reasoning",
    "auto-writing": "writing",
    "auto-translation": "translation",
    "auto-vision": "vision",
    "auto-tools": "tools",
}

_LOGICAL_CAPABILITY_OVERRIDE: dict[str, set[str]] = {
    "auto-vision": {"vision"},
    "auto-tools": {"tools", "json"},
}

_LOGICAL_MODELS = {
    "auto", "auto-fast", "auto-best",
    "auto-coding", "auto-reasoning", "auto-writing",
    "auto-translation", "auto-vision", "auto-tools",
}

_QUALITY_FLOOR = {"easy": 75, "medium": 85, "hard": 0}


@dataclass
class RoutePlan:
    classification: RequestClassification
    eligible_routes: list[dict] = field(default_factory=list)
    selected_models: list[str] = field(default_factory=list)
    fallback_chain: list[dict] = field(default_factory=list)
    selected_route: dict | None = None
    decision: RouteDecision | None = None


def _is_logical_model(model: str) -> bool:
    return model in _LOGICAL_MODELS


def _is_explicit_provider_model(model: str) -> bool:
    return "/" in model and not _is_logical_model(model)


def _apply_logical_overrides(classification: RequestClassification, logical_model: str) -> RequestClassification:
    task_override = _LOGICAL_TASK_OVERRIDE.get(logical_model)
    if task_override:
        classification.task_type = task_override  # type: ignore[assignment]
        classification.matched_rules.append(f"logical_override:task={task_override}")
    cap_override = _LOGICAL_CAPABILITY_OVERRIDE.get(logical_model)
    if cap_override:
        classification.required_capabilities |= cap_override
        classification.matched_rules.append(f"logical_override:caps={cap_override}")
    return classification


def _compute_model_health(eligible_routes: list[dict], health_data: dict) -> dict:
    model_health: dict[str, dict] = {}
    for route in eligible_routes:
        model = route.get("canonical_model_name", "")
        if not model:
            continue
        route_id = route.get("id", 0)
        rh = health_data.get(route_id, {})
        if model not in model_health:
            model_health[model] = {"best_ttft_p95": float("inf"), "best_reliability_lcb": 0.0, "healthy_route_count": 0}
        mh = model_health[model]
        ttft = rh.get("ttft_p95_ms")
        if ttft is not None and ttft < mh["best_ttft_p95"]:
            mh["best_ttft_p95"] = ttft
        reliability = rh.get("reliability_lcb", 0.0)
        if reliability > mh["best_reliability_lcb"]:
            mh["best_reliability_lcb"] = reliability
        if rh.get("circuit_state", "closed") != "open":
            mh["healthy_route_count"] += 1
    return model_health


def _route_summary(route: dict) -> dict:
    return {
        "route_id": route.get("id"),
        "provider": route.get("provider_name"),
        "canonical_model": route.get("canonical_model_name"),
        "upstream_model_id": route.get("upstream_model_id"),
    }


def _load_static_scores() -> dict:
    settings = get_settings()
    yaml_path = settings.config_dir / "model_scores.yaml"
    return load_scores(yaml_path)


def _load_task_weights() -> dict:
    import yaml
    settings = get_settings()
    yaml_path = settings.config_dir / "routing_rules.yaml"
    if yaml_path.exists():
        try:
            raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return raw.get("routing", {}).get("task_weights", {})
        except Exception:
            logger.exception("Failed to parse routing_rules.yaml")
    return {}


async def make_route_plan(
    body: dict,
    client_permissions: list[str] | None = None,
) -> RoutePlan:
    start_time = time.time()
    requested_model = body.get("model", "auto") or "auto"

    features: RequestFeatures = extract_features(body)
    classification: RequestClassification = classify(features)

    logical_model = requested_model
    is_explicit_model = False
    is_provider_model = False
    explicit_provider: str | None = None
    explicit_upstream: str | None = None

    if _is_logical_model(requested_model):
        classification = _apply_logical_overrides(classification, requested_model)
    elif _is_explicit_provider_model(requested_model):
        parts = requested_model.split("/", 1)
        explicit_provider = parts[0]
        explicit_upstream = parts[1]
        is_provider_model = True
        logical_model = "explicit-provider"
    else:
        is_explicit_model = True
        logical_model = "explicit-model"

    try:
        all_routes = await RouteRepository.get_all_enabled()
    except Exception:
        logger.exception("Failed to load routes from database")
        all_routes = []

    try:
        health_data = await RouteHealthRepository.get_all()
    except Exception:
        logger.exception("Failed to load route health from database")
        health_data = {}

    static_scores = _load_static_scores()
    task_weights = _load_task_weights()

    # --- Explicit canonical model ---
    if is_explicit_model:
        canonical = normalize_model_name(requested_model)
        model_routes = [r for r in all_routes if r.get("canonical_model_name") == canonical]
        eligible, _w = filter_routes(model_routes, classification.required_capabilities,
                                    classification.minimum_context_length, client_permissions, health_data)
        allow_fallback = body.get("allow_fallback", False)
        if allow_fallback and len(eligible) < 2:
            other_routes = [r for r in all_routes if r.get("canonical_model_name") != canonical]
            other_eligible, _w2 = filter_routes(other_routes, classification.required_capabilities,
                                               classification.minimum_context_length, client_permissions, health_data)
            eligible = eligible + other_eligible
        selected_models = [canonical] if eligible else []
        fallback = build_fallback_chain(eligible, selected_models, health_data)
        selected_route = fallback[0] if fallback else None
        decision = RouteDecision(
            requested_model=requested_model, logical_model=logical_model,
            task_type=classification.task_type, difficulty=classification.difficulty,
            required_capabilities=classification.required_capabilities,
            candidate_models=selected_models,
            selected_canonical_model=canonical if selected_route else None,
            selected_route_id=selected_route.get("id") if selected_route else None,
            attempt_count=0,
            fallback_chain=[_route_summary(r) for r in fallback],
            final_status="planned" if selected_route else "no_route",
            total_latency_ms=round((time.time() - start_time) * 1000, 2),
        )
        await record_decision(decision)
        return RoutePlan(classification=classification, eligible_routes=eligible,
                         selected_models=selected_models, fallback_chain=fallback,
                         selected_route=selected_route, decision=decision)

    # --- Explicit provider/model ---
    if is_provider_model:
        provider_routes = [r for r in all_routes
                           if r.get("provider_name") == explicit_provider
                           and r.get("upstream_model_id") == explicit_upstream]
        allow_fallback = body.get("allow_fallback", False)
        if allow_fallback:
            eligible, _w = filter_routes(all_routes, classification.required_capabilities,
                                        classification.minimum_context_length, client_permissions, health_data)
            requested = [r for r in eligible if r.get("provider_name") == explicit_provider
                         and r.get("upstream_model_id") == explicit_upstream]
            others = [r for r in eligible if r not in requested]
            eligible = requested + others
            selected_models = list(dict.fromkeys(r.get("canonical_model_name", "") for r in eligible))
        else:
            eligible, _w = filter_routes(provider_routes, classification.required_capabilities,
                                        classification.minimum_context_length, client_permissions, health_data)
            selected_models = list(dict.fromkeys(r.get("canonical_model_name", "") for r in eligible))
        fallback = build_fallback_chain(eligible, selected_models, health_data)
        selected_route = fallback[0] if fallback else None
        decision = RouteDecision(
            requested_model=requested_model, logical_model=logical_model,
            task_type=classification.task_type, difficulty=classification.difficulty,
            required_capabilities=classification.required_capabilities,
            candidate_models=selected_models,
            selected_canonical_model=selected_route.get("canonical_model_name") if selected_route else None,
            selected_route_id=selected_route.get("id") if selected_route else None,
            attempt_count=0,
            fallback_chain=[_route_summary(r) for r in fallback],
            final_status="planned" if selected_route else "no_route",
            total_latency_ms=round((time.time() - start_time) * 1000, 2),
        )
        await record_decision(decision)
        return RoutePlan(classification=classification, eligible_routes=eligible,
                         selected_models=selected_models, fallback_chain=fallback,
                         selected_route=selected_route, decision=decision)

    # --- Full automatic routing ---
    eligible, _warming = filter_routes(all_routes, classification.required_capabilities,
                                       classification.minimum_context_length, client_permissions, health_data)
    if not eligible and _warming:
        eligible = _warming

    grouped = group_by_canonical_model(eligible)
    candidates = score_models(grouped, classification.task_type, static_scores, task_weights)

    model_health = _compute_model_health(eligible, health_data)
    health_with_models = {**health_data, "_model_health": model_health}

    selected_models = select_model_order(candidates, classification.difficulty, logical_model,
                                          health_with_models, _QUALITY_FLOOR)

    fallback = build_fallback_chain(eligible, selected_models, health_data)
    selected_route = fallback[0] if fallback else None

    decision = RouteDecision(
        requested_model=requested_model, logical_model=logical_model,
        task_type=classification.task_type, difficulty=classification.difficulty,
        required_capabilities=classification.required_capabilities,
        candidate_models=selected_models,
        selected_canonical_model=selected_route.get("canonical_model_name") if selected_route else None,
        selected_route_id=selected_route.get("id") if selected_route else None,
        attempt_count=0,
        fallback_chain=[_route_summary(r) for r in fallback],
        final_status="planned" if selected_route else "no_route",
        total_latency_ms=round((time.time() - start_time) * 1000, 2),
    )
    await record_decision(decision)

    return RoutePlan(classification=classification, eligible_routes=eligible,
                     selected_models=selected_models, fallback_chain=fallback,
                     selected_route=selected_route, decision=decision)


# ---------------------------------------------------------------------------
# Public helpers for the API layer
# ---------------------------------------------------------------------------

async def get_available_models(client_permissions: list[str] | None = None) -> list[dict]:
    """Return list of available models for /v1/models endpoint."""
    from app.storage.repositories import RouteRepository

    _LOGICAL_MODELS = {
        "auto", "auto-fast", "auto-best", "auto-general",
        "auto-coding", "auto-reasoning", "auto-writing",
        "auto-translation", "auto-vision", "auto-tools",
    }

    models_list = []
    for lm in sorted(_LOGICAL_MODELS):
        models_list.append({"id": lm, "object": "model", "owned_by": "gateway"})

    routes = await RouteRepository.get_all_enabled()
    seen = set()
    for r in routes:
        canonical = r.get("canonical_model_name", "")
        if canonical and canonical not in seen:
            if client_permissions and canonical not in client_permissions:
                continue
            seen.add(canonical)
            models_list.append({
                "id": canonical,
                "object": "model",
                "owned_by": r.get("provider_name", "unknown"),
                "context_length": r.get("context_length", 32768),
            })

    for r in routes:
        combo = f"{r.get('provider_name', '')}/{r.get('upstream_model_id', '')}"
        models_list.append({
            "id": combo,
            "object": "model",
            "owned_by": r.get("provider_name", "unknown"),
        })

    return models_list
