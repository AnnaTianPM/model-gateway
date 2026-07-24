"""Streaming proxy with safety guarantees."""

from __future__ import annotations

import copy
import json
import logging
import time
from typing import Any, AsyncGenerator

import httpx
from fastapi.responses import StreamingResponse

from app.providers.errors import (
    ErrorType,
    classify_exception,
    classify_http_error,
)
from app.proxy.response_normalizer import restore_hermes_text
from app.proxy.usage import record_usage

logger = logging.getLogger(__name__)


async def proxy_streaming(
    candidates: list[tuple[dict, str]],
    body: dict[str, Any],
    http_client: httpx.AsyncClient,
    max_attempts: int = 4,
    diagnostic_headers: dict[str, str] | None = None,
) -> StreamingResponse:
    """Forward a streaming chat completion with first-token failover.

    - Before first token: can switch to next candidate.
    - After first token: no model switching, safe termination on error.
    """
    headers = diagnostic_headers or {}

    async def generate() -> AsyncGenerator[str, None]:
        attempts = 0
        first_token_sent = False
        usage_obj = None

        for provider, model in candidates:
            if attempts >= max_attempts:
                break
            if first_token_sent:
                break
            attempts += 1

            route_key = f"{provider['name']}||{model}"
            req_body = copy.deepcopy(body)
            req_body["model"] = model
            req_body["stream"] = True

            url = provider["base_url"].rstrip("/") + "/chat/completions"
            req_headers = {
                "Authorization": f"Bearer {provider['api_key']}",
                "Content-Type": "application/json",
            }

            start_time = time.time()
            try:
                req = http_client.build_request("POST", url, json=req_body, headers=req_headers)
                resp = await http_client.send(req, stream=True)
            except httpx.RequestError as e:
                logger.warning("stream connect error to %s: %s", provider["name"], e)
                await _record_health(route_key, "live", "network_error", 0, 0)
                continue

            if resp.status_code != 200:
                try:
                    await resp.aread()
                except Exception:
                    pass
                await resp.aclose()

                error_type = classify_http_error(resp.status_code)
                logger.warning(
                    "upstream stream error %d from %s",
                    resp.status_code,
                    provider["name"],
                )
                await _record_health(route_key, "live", error_type.value, resp.status_code, 0)
                continue

            stream_ok = True
            try:
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if not line.startswith("data: "):
                        yield line + "\n"
                        continue

                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        yield "data: [DONE]\n\n"
                        break

                    try:
                        obj = json.loads(data_str)
                        if obj.get("usage"):
                            usage_obj = obj["usage"]
                        if "model" in obj and isinstance(obj["model"], str):
                            obj["model"] = f"{provider['name']} · {model}"

                        choices = obj.get("choices") or []
                        if choices:
                            delta = choices[0].get("delta") or {}
                            content = delta.get("content")
                            if isinstance(content, str) and content:
                                first_token_sent = True

                        out = json.dumps(obj, ensure_ascii=False)
                        out = restore_hermes_text(out)
                        yield "data: " + out + "\n\n"
                    except json.JSONDecodeError:
                        yield line + "\n"

                # Stream completed successfully
                total_ms = round((time.time() - start_time) * 1000)
                await _record_health(route_key, "live", "success", 200, total_ms)

                if usage_obj:
                    await record_usage(
                        model=model,
                        provider=provider["name"],
                        prompt_tokens=usage_obj.get("prompt_tokens", 0),
                        completion_tokens=usage_obj.get("completion_tokens", 0),
                    )
                return

            except Exception:
                stream_ok = False
                total_ms = round((time.time() - start_time) * 1000)
                logger.exception(
                    "stream interrupted from %s (first_token_sent=%s)",
                    provider["name"],
                    first_token_sent,
                )

                if first_token_sent:
                    # After first token: safe termination, NO cross-model continuation
                    await _record_health(route_key, "live", "stream_error", 0, total_ms)
                    yield _error_event(
                        "stream_error_after_first_token",
                        "Stream interrupted after content was already delivered.",
                    )
                    yield "data: [DONE]\n\n"
                    return
                else:
                    # Before first token: can try next candidate
                    await _record_health(route_key, "live", "stream_error", 0, total_ms)
                    continue
            finally:
                if stream_ok:
                    try:
                        await resp.aclose()
                    except Exception:
                        pass

        # All candidates exhausted
        if not first_token_sent:
            yield _error_event(
                "all_candidates_failed",
                "All candidate models failed to produce a response.",
            )
            yield "data: [DONE]\n\n"

    response = StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            **headers,
        },
    )
    return response


def _error_event(error_type: str, message: str) -> str:
    """Generate an OpenAI-compatible SSE error event."""
    event = {
        "error": {
            "type": error_type,
            "message": message,
        }
    }
    return "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"


async def _record_health(
    route_key: str, source: str, status: str, http_status: int, latency_ms: int
) -> None:
    """Record health event (best-effort)."""
    try:
        from app.observability.events import record_health_event
        await record_health_event(route_key, source, status, http_status=http_status, latency_ms=latency_ms)
    except Exception:
        pass
