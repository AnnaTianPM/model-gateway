"""Circuit breaker state machine."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    open_until: float = 0.0
    half_open_successes: int = 0

    def is_available(self) -> bool:
        """Check if the route is available for requests."""
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.time() >= self.open_until:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        if self.state == CircuitState.HALF_OPEN:
            return True
        return False

    def should_try_half_open(self) -> bool:
        """Check if circuit should transition from OPEN to HALF_OPEN."""
        return self.state == CircuitState.OPEN and time.time() >= self.open_until

    def record_success(self) -> None:
        """Record a successful request."""
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_successes += 1
            if self.half_open_successes >= 2:
                self.state = CircuitState.CLOSED
                self.consecutive_failures = 0
                self.open_until = 0.0
                self.half_open_successes = 0
        else:
            self.consecutive_failures = 0
            self.state = CircuitState.CLOSED

    def record_failure(self, threshold: int = 3, recovery_seconds: int = 60) -> None:
        """Record a failed request."""
        self.consecutive_failures += 1
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self.open_until = time.time() + recovery_seconds
            self.half_open_successes = 0
        elif self.consecutive_failures >= threshold:
            self.state = CircuitState.OPEN
            self.open_until = time.time() + recovery_seconds

    def to_dict(self) -> dict:
        return {
            "circuit_state": self.state.value,
            "consecutive_failures": self.consecutive_failures,
            "circuit_open_until": self.open_until if self.open_until else None,
        }
