from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# All supported task / dimension types.
TASK_TYPES = frozenset(
    {
        "general",
        "coding",
        "reasoning",
        "math",
        "writing",
        "translation",
        "chinese",
        "tool_calling",
        "vision",
        "json",
    }
)

# Fallback context length when a model has no explicit value.
DEFAULT_CONTEXT_LENGTH = 32768


def load_scores(yaml_path: Path) -> dict:
    """Load ``model_scores.yaml`` and return the parsed dict.

    The returned dict preserves the YAML top-level structure (``version``,
    ``updated_at``, ``models``).  If the file is missing or unparseable an
    empty skeleton ``{"models": {}}`` is returned so callers can proceed
    without special-casing.
    """
    if not yaml_path.exists():
        logger.warning("Model scores file not found: %s", yaml_path)
        return {"models": {}}

    try:
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        logger.error("Failed to parse model scores YAML %s: %s", yaml_path, exc)
        return {"models": {}}

    if data is None:
        return {"models": {}}
    if "models" not in data or not isinstance(data["models"], dict):
        data["models"] = {}
    return data


def get_task_score(model_name: str, task_type: str, scores: dict) -> float:
    """Return the 0–100 score for *task_type* on *model_name*.

    Returns ``0.0`` when the model or task type is absent.
    """
    models = scores.get("models", {})
    model_entry = models.get(model_name, {})
    model_scores = model_entry.get("scores", {})
    return float(model_scores.get(task_type, 0))


def compute_weighted_score(
    model_name: str,
    task_type: str,
    scores: dict,
    weights: dict,
) -> float:
    """Compute a weighted average score using task weights from routing config.

    *weights* maps dimension names to their weight, e.g.::

        {"coding": 0.70, "reasoning": 0.15, "tool_calling": 0.10, "json": 0.05}

    The *task_type* parameter is accepted for API symmetry but the actual
    dimensions used are solely determined by *weights*.  When *weights* is
    empty the raw score for *task_type* is returned.
    """
    if not weights:
        return get_task_score(model_name, task_type, scores)

    total_weight = 0.0
    weighted_sum = 0.0

    for dimension, weight in weights.items():
        score = get_task_score(model_name, dimension, scores)
        weighted_sum += score * weight
        total_weight += weight

    if total_weight == 0:
        return 0.0

    return weighted_sum / total_weight


def get_all_scores(model_name: str, scores: dict) -> dict[str, float]:
    """Return all 10 task scores for *model_name* as a dict.

    Missing scores are reported as ``0.0``.
    """
    models = scores.get("models", {})
    model_entry = models.get(model_name, {})
    model_scores = model_entry.get("scores", {})

    return {
        task_type: float(model_scores.get(task_type, 0))
        for task_type in TASK_TYPES
    }


def get_context_length(model_name: str, scores: dict) -> int:
    """Return the context length for *model_name* from scores data.

    Defaults to :data:`DEFAULT_CONTEXT_LENGTH` (32768) when unspecified.
    """
    models = scores.get("models", {})
    model_entry = models.get(model_name, {})
    ctx = model_entry.get("context_length")
    if ctx is not None:
        return int(ctx)
    return DEFAULT_CONTEXT_LENGTH
