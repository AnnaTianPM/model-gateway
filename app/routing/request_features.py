"""Request feature extraction from OpenAI chat-completion request bodies.

Estimates input tokens using a character-based heuristic:
  * English / Latin text: ~4 chars per token.
  * CJK (Chinese, Japanese, Korean) text: ~2 chars per token.
A 20 % safety margin is added to the estimate.

``minimum_context_length`` = estimated_input_tokens + max_tokens + 20 % margin.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# CJK Unified Ideographs + common extensions (sufficient for estimation).
_CJK_PATTERN = re.compile(
    r"[\u4e00-\u9fff"          # CJK Unified Ideographs
    r"\u3400-\u4dbf"            # CJK Extension A
    r"\u3040-\u30ff"            # Hiragana + Katakana
    r"\uac00-\ud7af"            # Hangul Syllables
    r"]"
)

# Default max_tokens when the client does not specify one.
_DEFAULT_MAX_TOKENS = 4096


def _extract_text_from_content(content) -> str:
    """Extract plain text from a message ``content`` field.

    ``content`` can be a string or a list of content parts (OpenAI vision format).
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    parts.append(part.get("text", ""))
                elif part.get("type") == "image_url":
                    # We don't extract text from images, but note their presence.
                    pass
            elif isinstance(part, str):
                parts.append(part)
        return "\n".join(parts)
    return ""


def _has_image_content(content) -> bool:
    """Check whether a message content contains an image_url part."""
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "image_url":
                return True
    return False


def estimate_tokens(text: str) -> int:
    """Estimate the number of tokens in *text*.

    Heuristic:
      * CJK characters: ~2 chars / token.
      * Other characters: ~4 chars / token.
      * +20 % safety margin.
    """
    if not text:
        return 0

    cjk_count = len(_CJK_PATTERN.findall(text))
    non_cjk_count = len(text) - cjk_count

    # CJK: ~2 chars/token → cjk_count / 2
    # Non-CJK: ~4 chars/token → non_cjk_count / 4
    raw_tokens = (cjk_count / 2.0) + (non_cjk_count / 4.0)
    estimated = int(raw_tokens * 1.2)  # +20 % safety margin
    return max(estimated, 1)


def _get_max_tokens(body: dict) -> int:
    """Extract max_tokens / max_completion_tokens from the request body."""
    for key in ("max_tokens", "max_completion_tokens"):
        val = body.get(key)
        if isinstance(val, int) and val > 0:
            return val
    return _DEFAULT_MAX_TOKENS


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field


@dataclass
class RequestFeatures:
    """Structured features extracted from a chat-completion request body."""

    messages_text: str
    has_images: bool
    has_tools: bool
    response_format: dict | None
    max_tokens: int
    tools_count: int
    estimated_input_tokens: int
    minimum_context_length: int


def extract_features(body: dict) -> RequestFeatures:
    """Extract request features from an OpenAI chat-completion body.

    Parameters
    ----------
    body:
        The parsed JSON body of a ``POST /v1/chat/completions`` request.

    Returns
    -------
    RequestFeatures
    """
    messages = body.get("messages", [])
    if not isinstance(messages, list):
        messages = []

    # --- Collect text and detect images ---
    text_parts: list[str] = []
    has_images = False

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        text_parts.append(_extract_text_from_content(content))
        if _has_image_content(content):
            has_images = True

    messages_text = "\n".join(text_parts)

    # --- Tools ---
    tools = body.get("tools", [])
    if not isinstance(tools, list):
        tools = []
    has_tools = len(tools) > 0
    tools_count = len(tools)

    # --- Response format ---
    response_format = body.get("response_format")
    if not isinstance(response_format, dict):
        response_format = None

    # --- max_tokens ---
    max_tokens = _get_max_tokens(body)

    # --- Token estimation ---
    estimated_input_tokens = estimate_tokens(messages_text)

    # --- Minimum context length ---
    # estimated_input + max_tokens + 20 % margin
    minimum_context_length = int((estimated_input_tokens + max_tokens) * 1.2)

    return RequestFeatures(
        messages_text=messages_text,
        has_images=has_images,
        has_tools=has_tools,
        response_format=response_format,
        max_tokens=max_tokens,
        tools_count=tools_count,
        estimated_input_tokens=estimated_input_tokens,
        minimum_context_length=minimum_context_length,
    )
