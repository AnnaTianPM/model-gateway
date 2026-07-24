"""Route decision recording."""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RouteDecision:
    """Record of a routing decision for a single request."""

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    client_key_id: int | None = None
    requested_model: str = ""
    logical_model: str = ""
    task_type: str = ""
    difficulty: str = ""
    required_capabilities: list[str] = field(default_factory=list)
    candidate_models: list[str] = field(default_factory=list)
    selected_canonical_model: str = ""
    selected_route_id: int | None = None
    attempt_count: int = 0
    fallback_chain: list[str] = field(default_factory=list)
    final_status: str = ""
    total_latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "timestamp": self.timestamp,
            "client_key_id": self.client_key_id,
            "requested_model": self.requested_model,
            "logical_model": self.logical_model,
            "task_type": self.task_type,
            "difficulty": self.difficulty,
            "required_capabilities": self.required_capabilities,
            "candidate_models": self.candidate_models,
            "selected_canonical_model": self.selected_canonical_model,
            "selected_route_id": self.selected_route_id,
            "attempt_count": self.attempt_count,
            "fallback_chain": self.fallback_chain,
            "final_status": self.final_status,
            "total_latency_ms": self.total_latency_ms,
        }


async def record_decision(decision: RouteDecision) -> None:
    """Save a route decision to the database (best-effort)."""
    try:
        from app.storage.repositories import RouteDecisionRepository
        await RouteDecisionRepository.insert(decision.to_dict())
    except Exception:
        logger.debug("record_decision failed (best-effort)", exc_info=True)
