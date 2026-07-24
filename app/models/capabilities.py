from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Capabilities:
    """Boolean capability flags for a canonical model."""

    stream: bool = False
    tools: bool = False
    json: bool = False
    vision: bool = False
    reasoning: bool = False


def get_capabilities(canonical_name: str, scores_data: dict) -> Capabilities:
    """Look up capabilities for *canonical_name* from loaded YAML scores data.

    The *scores_data* dict is expected to follow the ``model_scores.yaml``
    structure::

        models:
          <canonical_name>:
            capabilities:
              stream: true
              tools: true
              ...

    Missing models or missing capability keys default to ``False``.
    """
    models = scores_data.get("models", {})
    model_entry = models.get(canonical_name, {})
    caps = model_entry.get("capabilities", {})

    return Capabilities(
        stream=caps.get("stream", False),
        tools=caps.get("tools", False),
        json=caps.get("json", False),
        vision=caps.get("vision", False),
        reasoning=caps.get("reasoning", False),
    )


def has_capability(capabilities: Capabilities, required: set[str]) -> bool:
    """Return ``True`` only when *every* capability in *required* is present.

    Each element of *required* must be one of the attribute names on
    :class:`Capabilities` (``stream``, ``tools``, ``json``, ``vision``,
    ``reasoning``).
    """
    for cap in required:
        if not getattr(capabilities, cap, False):
            return False
    return True
