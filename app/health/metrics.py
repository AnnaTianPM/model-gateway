"""Multi-window health metric aggregation.

Computes per-route aggregate health from raw health events across three
time windows: 5 minutes, 1 hour, and 24 hours.

For each window:
  * successes / failures counts
  * availability (success / total)
  * P50 / P95 latency
  * P50 / P95 TTFT (time to first token)
  * reliability LCB (Wilson lower bound)

Also integrates circuit-breaker state transitions.
"""

from __future__ import annotations

import logging
import time

from app.health.circuit_breaker import CircuitBreaker, CircuitState
from app.health.reliability import compute_reliability_lcb

logger = logging.getLogger(__name__)

# Window durations in seconds.
WINDOW_5M = 300
WINDOW_1H = 3600
WINDOW_24H = 86400

# Failure statuses that count against reliability.
_FAILURE_STATUSES = frozenset({
    "timeout",
    "rate_limited",
    "server_error",
    "network_error",
    "error",
    "invalid_response",
    "stream_error",
})

# Statuses that do NOT count as health failures (client-caused or content-policy).
_NON_PENALIZING_STATUSES = frozenset({
    "auth_error",  # handled separately (disable route, not count as failure)
})


def _percentile(values: list[float], p: float) -> float | None:
    """Compute the p-th percentile of *values* (linear interpolation).

    Returns ``None`` if *values* is empty.
    """
    if not values:
        return None
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    k = (n - 1) * p / 100.0
    f = int(k)
    c = k - f
    if f + 1 < n:
        return round(sorted_vals[f] + (sorted_vals[f + 1] - sorted_vals[f]) * c, 2)
    return round(sorted_vals[f], 2)


def _is_failure(status: str) -> bool:
    """Determine whether a status counts as a health failure."""
    return status in _FAILURE_STATUSES


def _is_success(status: str) -> bool:
    """Determine whether a status counts as a success."""
    return status == "success"


def _aggregate_window(events: list[dict], window_seconds: float) -> dict:
    """Aggregate events within a time window.

    Returns a dict with successes, failures, availability, latency/TTFT
    percentiles.
    """
    now = time.time()
    cutoff = now - window_seconds
    window_events = [e for e in events if e.get("timestamp", 0) >= cutoff]

    successes = 0
    failures = 0
    latencies: list[float] = []
    ttfts: list[float] = []

    for e in window_events:
        status = e.get("status", "unknown")
        if _is_success(status):
            successes += 1
            lat = e.get("latency_ms")
            if lat is not None:
                latencies.append(float(lat))
            ttft = e.get("ttft_ms")
            if ttft is not None:
                ttfts.append(float(ttft))
        elif _is_failure(status):
            failures += 1

    total = successes + failures
    availability = successes / total if total > 0 else 1.0

    return {
        "successes": successes,
        "failures": failures,
        "total": total,
        "availability": round(availability, 4),
        "latency_p50_ms": _percentile(latencies, 50),
        "latency_p95_ms": _percentile(latencies, 95),
        "ttft_p50_ms": _percentile(ttfts, 50),
        "ttft_p95_ms": _percentile(ttfts, 95),
    }


def aggregate_health(events: list[dict]) -> dict:
    """Compute multi-window aggregate health from a list of health events.

    Parameters
    ----------
    events:
        List of health-event dicts (each must contain ``timestamp`` and
        ``status``).

    Returns
    -------
    dict
        Aggregated metrics including 5m/1h/24h windows, reliability LCB,
        and circuit-breaker state.
    """
    if not events:
        return {
            "last_status": None,
            "last_checked_at": None,
            "successes_5m": 0, "failures_5m": 0,
            "successes_1h": 0, "failures_1h": 0,
            "successes_24h": 0, "failures_24h": 0,
            "availability_5m": 1.0,
            "availability_1h": 1.0,
            "availability_24h": 1.0,
            "reliability_lcb": 0.0,
            "latency_p50_ms": None,
            "latency_p95_ms": None,
            "ttft_p50_ms": None,
            "ttft_p95_ms": None,
            "consecutive_failures": 0,
            "circuit_state": "closed",
            "circuit_open_until": None,
            "cooldown_reason": None,
        }

    # Sort events by timestamp ascending
    sorted_events = sorted(events, key=lambda e: e.get("timestamp", 0))

    # Last status and timestamp
    last_event = sorted_events[-1]
    last_status = last_event.get("status")
    last_checked_at = last_event.get("timestamp", time.time())

    # Window aggregates
    w5m = _aggregate_window(sorted_events, WINDOW_5M)
    w1h = _aggregate_window(sorted_events, WINDOW_1H)
    w24h = _aggregate_window(sorted_events, WINDOW_24H)

    # Reliability LCB from 5m window (most recent)
    reliability_lcb = compute_reliability_lcb(w5m["successes"], w5m["failures"])

    # Circuit breaker: compute state from recent consecutive failures
    # Walk backwards through sorted events to find the current streak.
    consecutive_failures = 0
    last_failure_ts: float = 0.0
    for e in reversed(sorted_events):
        status = e.get("status", "unknown")
        if _is_success(status):
            break  # consecutive failures interrupted by a success
        if _is_failure(status):
            consecutive_failures += 1
            if not last_failure_ts:
                last_failure_ts = e.get("timestamp", 0.0)

    # Use CircuitBreaker to determine state, then read its values
    breaker = CircuitBreaker()
    breaker.consecutive_failures = consecutive_failures

    circuit_threshold = 3
    recovery_seconds = 60
    if consecutive_failures >= circuit_threshold:
        if last_failure_ts and time.time() < last_failure_ts + recovery_seconds:
            breaker.state = CircuitState.OPEN
            breaker.open_until = last_failure_ts + recovery_seconds
        else:
            breaker.state = CircuitState.HALF_OPEN
    else:
        breaker.state = CircuitState.CLOSED

    # Determine cooldown reason from last failure
    cooldown_reason = None
    if last_status == "rate_limited":
        cooldown_reason = "rate_limited"
    elif last_status == "auth_error":
        cooldown_reason = "auth_error"

    return {
        "last_status": last_status,
        "last_checked_at": last_checked_at,
        "successes_5m": w5m["successes"],
        "failures_5m": w5m["failures"],
        "successes_1h": w1h["successes"],
        "failures_1h": w1h["failures"],
        "successes_24h": w24h["successes"],
        "failures_24h": w24h["failures"],
        "availability_5m": w5m["availability"],
        "availability_1h": w1h["availability"],
        "availability_24h": w24h["availability"],
        "reliability_lcb": round(reliability_lcb, 4),
        "latency_p50_ms": w5m["latency_p50_ms"],
        "latency_p95_ms": w5m["latency_p95_ms"],
        "ttft_p50_ms": w5m["ttft_p50_ms"],
        "ttft_p95_ms": w5m["ttft_p95_ms"],
        "consecutive_failures": breaker.consecutive_failures,
        "circuit_state": breaker.state.value,
        "circuit_open_until": breaker.open_until if breaker.open_until else None,
        "cooldown_reason": cooldown_reason,
    }


async def update_route_health(route_id: int, events: list[dict]) -> dict:
    """Aggregate health events for a route and persist to the database.

    Parameters
    ----------
    route_id:
        The provider-route ID.
    events:
        List of health-event dicts for this route.

    Returns
    -------
    dict
        The aggregated health state that was persisted.
    """
    from app.storage.repositories import RouteHealthRepository

    aggregated = aggregate_health(events)

    try:
        await RouteHealthRepository.upsert(route_id, aggregated)
        logger.debug(
            "Updated route_health for route %d: avail_5m=%.2f, lcb=%.2f, circuit=%s",
            route_id,
            aggregated["availability_5m"],
            aggregated["reliability_lcb"],
            aggregated["circuit_state"],
        )
    except Exception:
        logger.exception("Failed to upsert route_health for route %d", route_id)

    return aggregated
