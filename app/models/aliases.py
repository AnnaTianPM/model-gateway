from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Builtin aliases derived from upstream ``models_meta.json``.
# These are applied before normalisation so that e.g.
# ``mistralai/mistral-small-2603`` is first expanded to
# ``mistralai/mistral-small-4-119b-2603`` and *then* normalised to
# ``mistral-small-4-119b-2603``.
_BUILTIN_ALIASES: dict[str, str] = {
    "mistralai/mistral-small-2603": "mistralai/mistral-small-4-119b-2603",
    "mistralai/mistral-large-2512": "mistralai/mistral-large-3-675b-instruct-2512",
}


def _find_models_meta() -> Path | None:
    """Search for ``models_meta.json`` in plausible locations.

    Looks in the project root (parent of ``app/``) and the ``app/`` directory.
    """
    here = Path(__file__).resolve()
    candidates = [
        here.parent.parent.parent / "models_meta.json",  # project root
        here.parent.parent / "models_meta.json",         # app/
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def load_aliases() -> dict[str, str]:
    """Load model aliases, merging builtin aliases with external overrides.

    External overrides are read from the ``aliases`` key of
    ``models_meta.json`` if the file exists.  Builtin aliases serve as the
    baseline; entries in the file take precedence.
    """
    aliases = dict(_BUILTIN_ALIASES)

    meta_path = _find_models_meta()
    if meta_path is None:
        logger.debug("models_meta.json not found; using builtin aliases only")
        return aliases

    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        file_aliases = data.get("aliases", {})
        if isinstance(file_aliases, dict):
            aliases.update(file_aliases)
            logger.debug(
                "Loaded %d aliases from %s (total: %d)",
                len(file_aliases),
                meta_path,
                len(aliases),
            )
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load aliases from %s: %s", meta_path, exc)

    return aliases


def resolve_alias(model_id: str, aliases: dict[str, str]) -> str:
    """Return the alias target for *model_id*, or *model_id* if no alias exists."""
    return aliases.get(model_id, model_id)
