"""Health probes for active route monitoring.

A *probe* is a minimal, low-cost request sent to an upstream provider to
check route health. The basic probe sends a trivial chat completion and
measures latency / TTFT.

Special probes (tools, json, vision) run at lower frequency to verify
capability-specific endpoints without excessive token consumption.
"""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)

# A 1×1 transparent PNG (base64) used for vision probes.
_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQAB"
    "h6FO1AAAAABJRU5ErkJggg=="
)


def probe_payload() -> dict:
    """Return the basic probe request body.

    A minimal chat-completion request that costs almost nothing.
    """
    return {
        "messages": [{"role": "user", "content": "Reply only: OK"}],
        "max_tokens": 4,
        "temperature": 0,
        "stream": False,
    }


def tools_probe_payload() -> dict:
    """Return a minimal tool-calling probe request body."""
    return {
        "messages": [{"role": "user", "content": "What is the weather?"}],
        "max_tokens": 16,
        "temperature": 0,
        "stream": False,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather for a location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {"type": "string"},
                        },
                        "required": ["location"],
                    },
                },
            }
        ],
        "tool_choice": "auto",
    }


def json_probe_payload() -> dict:
    """Return a minimal JSON-mode probe request body."""
    return {
        "messages": [{"role": "user", "content": "Return {\"ok\": true}"}],
        "max_tokens": 16,
        "temperature": 0,
        "stream": False,
        "response_format": {"type": "json_object"},
    }


def vision_probe_payload() -> dict:
    """Return a minimal vision probe request body with a tiny image."""
    return {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What color? Reply in one word."},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{_TINY_PNG_B64}",
                        },
                    },
                ],
            }
        ],
        "max_tokens": 8,
        "temperature": 0,
        "stream": False,
    }


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

def classify_http_status(status_code: int) -> str:
    """Classify an HTTP status code into a health-event status."""
    if status_code == 200:
        return "success"
    if status_code in (401, 403):
        return "auth_error"
    if status_code == 429:
        return "rate_limited"
    if status_code == 408:
        return "timeout"
    if 500 <= status_code < 600:
        return "server_error"
    if 400 <= status_code < 500:
        # Other 4xx — likely client parameter error, not provider health
        return "invalid_response"
    return "unknown"


def classify_exception(exc: Exception) -> str:
    """Classify a network exception into a health-event status."""
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.ConnectError):
        return "network_error"
    if isinstance(exc, httpx.ReadError):
        return "network_error"
    return "error"


# ---------------------------------------------------------------------------
# Probe execution
# ---------------------------------------------------------------------------

async def probe_route(
    route: dict,
    http_client: httpx.AsyncClient,
    payload: dict | None = None,
    source: str = "probe",
    timeout: float = 30.0,
) -> dict:
    """Send a probe to a route and return a health-event dict.

    Parameters
    ----------
    route:
        Route dict with ``base_url``, ``upstream_model_id`` and optionally
        ``api_key`` (or ``encrypted_api_key`` / ``api_key_env_ref``).
    http_client:
        An ``httpx.AsyncClient`` instance.
    payload:
        Request body. Defaults to :func:`probe_payload`.
    source:
        Event source label (``"probe"`` or ``"live"``).
    timeout:
        Request timeout in seconds.

    Returns
    -------
    dict
        A health-event dict with keys: ``route_id``, ``timestamp``,
        ``source``, ``status``, ``http_status``, ``latency_ms``,
        ``ttft_ms``, ``total_ms``, ``input_tokens``, ``output_tokens``,
        ``error_code``.
    """
    if payload is None:
        payload = probe_payload()

    route_id = route.get("id", 0)
    base_url = route.get("base_url", "").rstrip("/")
    upstream_model = route.get("upstream_model_id", "")
    api_key = route.get("api_key") or route.get("decrypted_api_key") or ""

    if not base_url or not upstream_model:
        return {
            "route_id": route_id,
            "timestamp": time.time(),
            "source": source,
            "status": "invalid_response",
            "http_status": None,
            "latency_ms": 0,
            "ttft_ms": None,
            "total_ms": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "error_code": "missing_route_config",
        }

    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {**payload, "model": upstream_model}

    start = time.time()
    ttft_ms: float | None = None

    try:
        is_stream = body.get("stream", False)

        if is_stream:
            # For streaming probes, measure TTFT
            async with http_client.stream(
                "POST", url, json=body, headers=headers, timeout=timeout
            ) as resp:
                ttft_ms = round((time.time() - start) * 1000)
                status = classify_http_status(resp.status_code)

                # Read the stream to completion
                async for _ in resp.aiter_lines():
                    pass  # consume

                total_ms = round((time.time() - start) * 1000)

                event = {
                    "route_id": route_id,
                    "timestamp": time.time(),
                    "source": source,
                    "status": status,
                    "http_status": resp.status_code,
                    "latency_ms": total_ms,
                    "ttft_ms": ttft_ms,
                    "total_ms": total_ms,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "error_code": None if status == "success" else f"http_{resp.status_code}",
                }
                return event
        else:
            resp = await http_client.post(url, json=body, headers=headers, timeout=timeout)
            total_ms = round((time.time() - start) * 1000)
            status = classify_http_status(resp.status_code)

            input_tokens = 0
            output_tokens = 0
            error_code = None

            if status == "success":
                try:
                    data = resp.json()
                    usage = data.get("usage", {})
                    input_tokens = usage.get("prompt_tokens", 0) or 0
                    output_tokens = usage.get("completion_tokens", 0) or 0
                except Exception:
                    status = "invalid_response"
                    error_code = "invalid_json"
            else:
                error_code = f"http_{resp.status_code}"

            event = {
                "route_id": route_id,
                "timestamp": time.time(),
                "source": source,
                "status": status,
                "http_status": resp.status_code,
                "latency_ms": total_ms,
                "ttft_ms": total_ms,  # non-streaming: TTFT = total latency
                "total_ms": total_ms,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "error_code": error_code,
            }
            return event

    except httpx.TimeoutException as e:
        total_ms = round((time.time() - start) * 1000)
        return {
            "route_id": route_id,
            "timestamp": time.time(),
            "source": source,
            "status": "timeout",
            "http_status": None,
            "latency_ms": total_ms,
            "ttft_ms": ttft_ms,
            "total_ms": total_ms,
            "input_tokens": 0,
            "output_tokens": 0,
            "error_code": str(e)[:200],
        }
    except httpx.RequestError as e:
        total_ms = round((time.time() - start) * 1000)
        return {
            "route_id": route_id,
            "timestamp": time.time(),
            "source": source,
            "status": "network_error",
            "http_status": None,
            "latency_ms": total_ms,
            "ttft_ms": ttft_ms,
            "total_ms": total_ms,
            "input_tokens": 0,
            "output_tokens": 0,
            "error_code": str(e)[:200],
        }
    except Exception as e:
        total_ms = round((time.time() - start) * 1000)
        logger.exception("Unexpected probe error for route %s", route_id)
        return {
            "route_id": route_id,
            "timestamp": time.time(),
            "source": source,
            "status": "error",
            "http_status": None,
            "latency_ms": total_ms,
            "ttft_ms": ttft_ms,
            "total_ms": total_ms,
            "input_tokens": 0,
            "output_tokens": 0,
            "error_code": str(e)[:200],
        }
