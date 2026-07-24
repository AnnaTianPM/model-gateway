from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def normalize_model_name(model_id: str) -> str:
    """Strip the provider prefix (everything before the last ``/``) and lowercase.

    Examples::

        "deepseek-ai/deepseek-v4-flash"  -> "deepseek-v4-flash"
        "nvidia/nemotron-3-ultra-550b-a55b" -> "nemotron-3-ultra-550b-a55b"
        "glm-5.2"                         -> "glm-5.2"
    """
    return model_id.split("/")[-1].lower()


def get_canonical_name(
    model_id: str,
    aliases: dict[str, str] | None = None,
) -> str:
    """Resolve *model_id* to its canonical name.

    The alias table is consulted first (e.g. ``"mistralai/mistral-small-2603"``
    -> ``"mistralai/mistral-small-4-119b-2603"``).  If no alias matches the
    original *model_id* is passed through to :func:`normalize_model_name`.
    """
    if aliases:
        model_id = aliases.get(model_id, model_id)
    return normalize_model_name(model_id)


@dataclass
class CanonicalModel:
    """A canonical (provider-agnostic) model with metadata.

    Attributes mirror the ``canonical_models`` database table (see plan §5.2).
    """

    id: str
    canonical_name: str
    display_name: str
    family: str
    context_length: int
    max_output_tokens: int
    supports_stream: bool
    supports_tools: bool
    supports_json: bool
    supports_vision: bool
    supports_reasoning: bool
    enabled: bool = True
