"""Response normalization utilities."""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

# Hermes tool name compression/decompression
HERMES_MAP = [
    ("mcp_hermes_studio_use_hermes_studio_use_", "mcp_hsu_"),
    ("mcp_hermes_studio_devices_hermes_studio_lan_", "mcp_hsd_"),
    ("mcp_hermes_studio_api_hermes_studio_api_", "mcp_hsa_"),
]


def compress_hermes(obj: dict) -> dict:
    """Compress long Hermes tool names to reduce token usage."""
    s = json.dumps(obj, ensure_ascii=False)
    for long, short in HERMES_MAP:
        s = s.replace(long, short)
    return json.loads(s)


def restore_hermes_text(text: str) -> str:
    """Restore compressed Hermes tool names back to original."""
    for long, short in HERMES_MAP:
        text = text.replace(short, long)
    return text


def merge_reasoning(obj: dict) -> dict:
    """Preserve reasoning_content field without merging into content."""
    return obj


def has_image(body: dict) -> bool:
    """Check if messages contain image_url in the last user message."""
    msgs = body.get("messages", [])
    for i in range(len(msgs) - 1, -1, -1):
        msg = msgs[i]
        if isinstance(msg, dict) and msg.get("role") == "user":
            content = msg.get("content")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "image_url":
                        return True
            return False
    return False
