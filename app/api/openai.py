"""OpenAI-compatible API endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.auth.client_keys import verify_client_key
from app.lifespan import get_http_client

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/models")
async def list_models(client_key=Depends(verify_client_key)):
    """List available models for the authenticated client."""
    from app.routing.service import get_available_models
    allowed = client_key.get("allowed_logical_models_json")
    import json
    if allowed:
        try:
            allowed = json.loads(allowed)
        except (json.JSONDecodeError, TypeError):
            allowed = None
    else:
        allowed = None
    models = await get_available_models(client_permissions=allowed)
    return {"object": "list", "data": models}


@router.post("/chat/completions")
async def chat_completions(request: Request, client_key=Depends(verify_client_key)):
    """Proxy chat completion request with smart routing."""
    body = await request.json()
    stream = body.get("stream", False)
    requested_model = body.get("model", "auto")

    from app.routing.service import make_route_plan
    from app.proxy.chat import proxy_non_streaming
    from app.proxy.streaming import proxy_streaming

    allowed = client_key.get("allowed_logical_models_json")
    import json
    if allowed:
        try:
            allowed = json.loads(allowed)
        except (json.JSONDecodeError, TypeError):
            allowed = None
    else:
        allowed = None

    route_plan = await make_route_plan(
        body=body,
        client_permissions=allowed,
    )

    # Build candidates list: (provider_dict, model_id)
    candidates = route_plan.fallback_chain if route_plan.fallback_chain else []
    if not candidates:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "message": f"No available models for: {requested_model}",
                    "type": "gateway_error",
                }
            },
        )

    # Build provider dicts for the proxy layer
    proxy_candidates = []
    for route in candidates:
        provider_dict = {
            "name": route.get("provider_name", ""),
            "base_url": route.get("base_url", ""),
            "api_key": "",  # Will be decrypted in proxy layer
        }
        # Decrypt API key if available
        if route.get("encrypted_api_key"):
            try:
                from app.auth.crypto import decrypt_key
                provider_dict["api_key"] = decrypt_key(route["encrypted_api_key"])
            except Exception:
                logger.warning("Failed to decrypt key for %s", provider_dict["name"])
        proxy_candidates.append((provider_dict, route.get("upstream_model_id", "")))

    classification = route_plan.classification
    diagnostic_headers = {
        "X-Gateway-Request-Id": getattr(route_plan, "request_id", ""),
        "X-Gateway-Logical-Model": requested_model,
    }
    if hasattr(classification, "task_type"):
        diagnostic_headers["X-Gateway-Task"] = classification.task_type
        diagnostic_headers["X-Gateway-Difficulty"] = classification.difficulty
    elif isinstance(classification, dict):
        diagnostic_headers["X-Gateway-Task"] = classification.get("task_type", "general")
        diagnostic_headers["X-Gateway-Difficulty"] = classification.get("difficulty", "medium")

    http_client = get_http_client()

    if stream:
        body["stream"] = True
        return await proxy_streaming(
            candidates=proxy_candidates,
            body=body,
            http_client=http_client,
            diagnostic_headers=diagnostic_headers,
        )

    response = await proxy_non_streaming(
        candidates=proxy_candidates,
        body=body,
        http_client=http_client,
    )

    for key, value in diagnostic_headers.items():
        response.headers[key] = value

    return response
