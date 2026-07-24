"""Event recording helpers for health events and route decisions.

These functions provide a convenient API for persisting observability data
without requiring callers to know the repository internals.
"""

from __future__ import annotations

import logging
import time

from app.storage.repositories import (
    HealthEventRepository,
    RouteDecisionRepository,
)

logger = logging.getLogger(__name__)


async def record_health_event(
    route_id: int,
    source: str,
    status: str,
    *,
    http_status: int | None = None,
    latency_ms: float | None = None,
    ttft_ms: float | None = None,
    total_ms: float | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    error_code: str | None = None,
    timestamp: float | None = None,
) -> int:
    """Record a health event to the database.

    Parameters
    ----------
    route_id:
        The provider-route ID.
    source:
        Event source — ``"probe"`` or ``"live"``.
    status:
        Event status — ``success``, ``timeout``, ``rate_limited``,
        ``auth_error``, ``server_error``, ``invalid_response``, etc.
    http_status:
        HTTP status code from the upstream response (if applicable).
    latency_ms:
        Total request latency in milliseconds.
    ttft_ms:
        Time to first token in milliseconds (streaming only).
    total_ms:
        Total wall-clock time in milliseconds.
    input_tokens:
        Prompt token count from upstream usage.
    output_tokens:
        Completion token count from upstream usage.
    error_code:
        Error code or short detail string.
    timestamp:
        Event timestamp (defaults to ``time.time()``).

    Returns
    -------
    int
        The inserted row ID, or ``0`` on failure.
    """
    event = {
        "route_id": route_id,
        "timestamp": timestamp or time.time(),
        "source": source,
        "status": status,
        "http_status": http_status,
        "latency_ms": latency_ms,
        "ttft_ms": ttft_ms,
        "total_ms": total_ms or latency_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "error_code": error_code,
    }

    try:
        row_id = await HealthEventRepository.insert(event)
        logger.debug(
            "Recorded health event: route=%d source=%s status=%s",
            route_id, source, status,
        )
        return row_id
    except Exception:
        logger.exception("Failed to record health event for route %d", route_id)
        return 0


async def record_route_decision(decision: dict) -> int:
    """Record a route decision to the database.

    Parameters
    ----------
    decision:
        A dict containing the decision fields (see
        :class:`app.routing.decision.RouteDecision`).

    Returns
    -------
    int
        The inserted row ID, or ``0`` on failure.
    """
    try:
        row_id = await RouteDecisionRepository.insert(decision)
        logger.debug(
            "Recorded route decision: request_id=%s",
            decision.get("request_id", "?"),
        )
        return row_id
    except Exception:
        logger.exception("Failed to record route decision")
        return 0
