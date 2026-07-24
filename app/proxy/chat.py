"""Non-streaming chat proxy with failover."""

from __future__ import annotations

import copy
import json
import logging
import time
from typing import Any

import httpx
from fastapi.responses import JSONResponse

from app.providers.errors import (
    ErrorType,
    classify_exception,
    classify_http_error,
    is_content_filtered,
    is_disabling,
    is_retryable,
)
from app.proxy.response_normalizer import (
    merge_reasoning,
    restore_hermes_text,
)
from app.proxy.usage import record_usage

logger = logging.getLogger(__name__)


async def proxy_non_streaming(
    candidates: list[tuple[dict, str]],
    body: dict[str, Any],
    http_client: httpx.AsyncClient,
    max_attempts: int = 4,
) -> JSONResponse:
    """Forward a non-streaming chat completion with failover.

    Args:
        candidates: List of (provider_dict, model_id) tuples in fallback order.
        body: The OpenAI request body.
        http_client: Shared HTTP client.
        max_attempts: Maximum total attempts.

    Returns:
        JSONResponse with the upstream response or error.
    """
    last_error = None
    attempts = 0

    for provider, model in candidates:
        if attempts >= max_attempts:
            break
        attempts += 1

        route_key = f"{provider['name']}||{model}"
        req_body = copy.deepcopy(body)
        req_body["model"] = model
        req_body["stream"] = False

        url = provider["base_url"].rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {provider['api_key']}",
            "Content-Type": "application/json",
        }

        start_time = time.time()
        try:
            resp = await http_client.post(
                url, json=req_body, headers=headers, timeout=120
            )
            latency_ms = round((time.time() - start_time) * 1000)

            if resp.status_code >= 400:
                error_type = classify_http_error(resp.status_code)
                logger.warning(
                    "upstream %d from %s: %s",
                    resp.status_code,
                    provider["name"],
                    resp.text[:200],
                )
                last_error = f"upstream {resp.status_code}"

                # Record health event
                await _record_health_event(
                    route_key, "live", error_type, resp.status_code, latency_ms
                )

                if is_disabling(error_type):
                    logger.error(
                        "auth error from %s, route should be disabled",
                        provider["name"],
                    )
                continue

            try:
                parsed = json.loads(resp.text)
                parsed = merge_reasoning(parsed)
                parsed_str = json.dumps(parsed, ensure_ascii=False)
                parsed_str = restore_hermes_text(parsed_str)
                parsed = json.loads(parsed_str)

                # Record success
                await _record_health_event(
                    route_key, "live", ErrorType.UNKNOWN, resp.status_code, latency_ms,
                    status="success"
                )

                # Update model field for client
                parsed["model"] = f"{provider['name']} · {model}"

                # Record usage
                usage = parsed.get("usage") or {}
                await record_usage(
                    model=model,
                    provider=provider["name"],
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                )

                # Add diagnostic headers
                return JSONResponse(
                    content=parsed,
                    status_code=resp.status_code,
                    headers={
                        "X-Gateway-Provider": provider["name"],
                        "X-Gateway-Model": model,
                        "X-Gateway-Attempts": str(attempts),
                    },
                )
            except json.JSONDecodeError:
                logger.warning(
                    "upstream non-json from %s: %s",
                    provider["name"],
                    resp.text[:200],
                )
                last_error = f"upstream non-json ({resp.status_code})"
                await _record_health_event(
                    route_key, "live", ErrorType.INVALID_RESPONSE,
                    resp.status_code, latency_ms
                )
                continue

        except httpx.RequestError as e:
            latency_ms = round((time.time() - start_time) * 1000)
            error_type = classify_exception(e)
            logger.warning("forward error to %s: %s", provider["name"], e)
            last_error = str(e)
            await _record_health_event(
                route_key, "live", error_type, 0, latency_ms
            )
            continue
        except Exception:
            latency_ms = round((time.time() - start_time) * 1000)
            logger.exception("unexpected forward error to %s", provider["name"])
            last_error = "unexpected error"
            await _record_health_event(
                route_key, "live", ErrorType.UNKNOWN, 0, latency_ms
            )
            continue

    return JSONResponse(
        status_code=502,
        content={"error": {"message": f"All candidate models failed: {last_error}", "type": "gateway_error"}},
        headers={"X-Gateway-Attempts": str(attempts)},
    )


async def _record_health_event(
    route_key: str,
    source: str,
    error_type: ErrorType,
    http_status: int,
    latency_ms: int,
    status: str = "",
) -> None:
    """Record a health event (best-effort, does not raise)."""
    try:
        from app.observability.events import record_health_event as record
        if status:
            await record(route_key, source, status, http_status=http_status, latency_ms=latency_ms)
        else:
            status_str = "success" if error_type == ErrorType.UNKNOWN else error_type.value
            await record(route_key, source, status_str, http_status=http_status, latency_ms=latency_ms)
    except Exception:
        pass  # Health recording is best-effort
