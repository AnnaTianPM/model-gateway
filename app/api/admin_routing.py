"""Admin API for routing configuration and decision logs."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.admin import verify_admin

logger = logging.getLogger(__name__)

router = APIRouter()


class RoutingPreviewRequest(BaseModel):
    messages: list[dict]
    model: str = "auto"
    tools: list[dict] | None = None
    response_format: dict | None = None
    max_tokens: int | None = None


@router.get("/routing/decisions")
async def get_decisions(limit: int = 50, _=Depends(verify_admin)):
    """Get recent routing decisions."""
    from app.storage.db import get_db
    from app.storage.repositories import RouteDecisionRepository

    await get_db()
    return await RouteDecisionRepository.get_recent(limit=limit)


@router.post("/routing/preview")
async def routing_preview(req: RoutingPreviewRequest, _=Depends(verify_admin)):
    """Preview routing decision without actually calling upstream."""
    body = {"messages": req.messages, "model": req.model}
    if req.tools:
        body["tools"] = req.tools
    if req.response_format:
        body["response_format"] = req.response_format
    if req.max_tokens:
        body["max_tokens"] = req.max_tokens

    from app.routing.service import make_route_plan
    plan = await make_route_plan(body=body, client_permissions=None)

    # RoutePlan from the routing agent has: classification, eligible_routes,
    # selected_models, fallback_chain (list[dict]), selected_route, decision
    classification = plan.classification
    if hasattr(classification, "task_type"):
        cls_dict = {
            "task_type": classification.task_type,
            "difficulty": classification.difficulty,
            "required_capabilities": list(classification.required_capabilities),
            "estimated_input_tokens": getattr(classification, "estimated_input_tokens", 0),
            "minimum_context_length": getattr(classification, "minimum_context_length", 0),
        }
    else:
        cls_dict = classification

    fallback = plan.fallback_chain or []
    result = {
        "classification": cls_dict,
        "eligible_routes": [
            {"provider": r.get("provider_name", "?"), "model": r.get("upstream_model_id", "?")}
            for r in (plan.eligible_routes or [])
        ],
        "fallback_chain": [
            {"provider": r.get("provider_name", "?"), "model": r.get("upstream_model_id", "?")}
            for r in fallback
        ],
        "selected_models": plan.selected_models or [],
    }

    if plan.decision:
        result["request_id"] = plan.decision.request_id

    return result


@router.get("/routing/config")
async def get_routing_config(_=Depends(verify_admin)):
    """Get current routing configuration."""
    from app.settings import get_settings
    from pathlib import Path
    import yaml

    settings = get_settings()
    config_path = settings.config_dir / "routing_rules.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {"error": "Routing config not found"}
