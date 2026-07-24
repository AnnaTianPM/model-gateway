"""Reliability calculations using Beta posterior and Wilson lower bound."""

from __future__ import annotations

import math


def beta_posterior_mean(successes: int, failures: int, alpha: float = 5.0, beta: float = 1.0) -> float:
    """Compute the Beta posterior mean.

    post_mean = (successes + alpha) / (successes + failures + alpha + beta)
    """
    total = successes + failures + alpha + beta
    if total == 0:
        return 0.0
    return (successes + alpha) / total


def wilson_lower_bound(successes: int, failures: int, z: float = 1.96) -> float:
    """Compute the Wilson score interval lower bound.

    This is used as a conservative reliability estimate without requiring SciPy.
    """
    n = successes + failures
    if n == 0:
        return 0.0
    p = successes / n
    denominator = 1 + z * z / n
    center = p + z * z / (2 * n)
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return max(0.0, (center - spread) / denominator)


def compute_reliability_lcb(successes: int, failures: int) -> float:
    """Compute the reliability lower confidence bound using Wilson method."""
    return wilson_lower_bound(successes, failures)
