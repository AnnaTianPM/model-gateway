"""Base provider interface."""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ProviderConfig:
    """Configuration for a provider instance."""

    id: int
    name: str
    base_url: str
    api_key: str
    enabled: bool = True
    adapter_type: str = "openai_compatible"
    default_headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 120
    max_concurrency: int = 10


class BaseProvider(abc.ABC):
    """Abstract base class for provider adapters."""

    def __init__(self, config: ProviderConfig, http_client: httpx.AsyncClient):
        self.config = config
        self.http_client = http_client

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def base_url(self) -> str:
        return self.config.base_url

    def _build_headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        """Build request headers with authentication."""
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        headers.update(self.config.default_headers)
        if extra:
            headers.update(extra)
        return headers

    def _build_url(self, path: str) -> str:
        """Build full URL for a path."""
        return self.config.base_url.rstrip("/") + path

    @abc.abstractmethod
    async def chat_completion(
        self, body: dict[str, Any], model: str, stream: bool = False
    ) -> httpx.Response:
        """Send a chat completion request."""
        ...

    @abc.abstractmethod
    async def list_models(self) -> list[dict[str, Any]]:
        """Fetch available models from the provider."""
        ...

    @abc.abstractmethod
    async def verify_key(self) -> dict[str, Any]:
        """Verify the API key is valid."""
        ...
