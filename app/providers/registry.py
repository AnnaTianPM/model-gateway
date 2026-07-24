"""Provider registry for managing provider adapters."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.providers.base import BaseProvider, ProviderConfig
from app.providers.openai_compatible import OpenAICompatibleProvider

logger = logging.getLogger(__name__)

_ADAPTER_TYPES: dict[str, type[BaseProvider]] = {
    "openai_compatible": OpenAICompatibleProvider,
}


def register_adapter(adapter_type: str, adapter_class: type[BaseProvider]) -> None:
    """Register a custom provider adapter type."""
    _ADAPTER_TYPES[adapter_type] = adapter_class


def create_provider(config: ProviderConfig, http_client: httpx.AsyncClient) -> BaseProvider:
    """Create a provider adapter from config."""
    adapter_class = _ADAPTER_TYPES.get(config.adapter_type, OpenAICompatibleProvider)
    return adapter_class(config, http_client)


def provider_config_from_dict(data: dict[str, Any]) -> ProviderConfig:
    """Create ProviderConfig from a dictionary (e.g., database row)."""
    return ProviderConfig(
        id=data["id"],
        name=data["name"],
        base_url=data["base_url"],
        api_key=data.get("_decrypted_api_key", data.get("api_key", "")),
        enabled=data.get("enabled", True),
        adapter_type=data.get("adapter_type", "openai_compatible"),
        default_headers=data.get("default_headers", {}),
        timeout_seconds=data.get("timeout_seconds", 120),
        max_concurrency=data.get("max_concurrency", 10),
    )
