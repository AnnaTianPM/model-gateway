"""OpenAI-compatible provider adapter."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.providers.base import BaseProvider, ProviderConfig

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(BaseProvider):
    """Adapter for OpenAI-compatible API providers (NVIDIA, OpenRouter, etc.)."""

    async def chat_completion(
        self, body: dict[str, Any], model: str, stream: bool = False
    ) -> httpx.Response:
        """Send a chat completion request to the upstream provider."""
        url = self._build_url("/chat/completions")
        headers = self._build_headers()
        req_body = {**body, "model": model, "stream": stream}

        if stream:
            req = self.http_client.build_request(
                "POST", url, json=req_body, headers=headers
            )
            return await self.http_client.send(req, stream=True)

        return await self.http_client.post(
            url,
            json=req_body,
            headers=headers,
            timeout=httpx.Timeout(self.config.timeout_seconds, connect=10.0),
        )

    async def list_models(self) -> list[dict[str, Any]]:
        """Fetch available models from the provider."""
        url = self._build_url("/models")
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        try:
            resp = await self.http_client.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                model_list = data.get("data", data) if isinstance(data, dict) else data
                if isinstance(model_list, list):
                    return model_list
            return []
        except Exception:
            logger.exception("list_models failed for %s", self.config.name)
            return []

    async def verify_key(self) -> dict[str, Any]:
        """Verify the API key is valid by calling /models."""
        url = self._build_url("/models")
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        try:
            resp = await self.http_client.get(url, headers=headers, timeout=15)
            if resp.status_code in (401, 403):
                return {"ok": False, "detail": f"Key invalid (HTTP {resp.status_code})"}
            if resp.status_code == 200:
                return {"ok": True, "detail": "Connection successful"}
            return {"ok": False, "detail": f"Upstream returned HTTP {resp.status_code}"}
        except httpx.RequestError as e:
            return {"ok": False, "detail": f"Connection failed: {str(e)[:150]}"}
        except Exception as e:
            return {"ok": False, "detail": f"Verify error: {str(e)[:150]}"}


def is_chat_model(model_id: str, non_chat_keywords: list[str]) -> bool:
    """Check if a model ID is a chat/completion model."""
    lower = model_id.lower()
    return not any(kw in lower for kw in non_chat_keywords)


def is_free_model(model_info: dict) -> bool:
    """Check if a model is free based on pricing."""
    pricing = model_info.get("pricing", {})
    prompt_price = pricing.get("prompt", "")
    completion_price = pricing.get("completion", "")
    try:
        if float(prompt_price) == 0 and float(completion_price) == 0:
            return True
    except (ValueError, TypeError):
        pass
    return False


def is_free_by_name(model_id: str) -> bool:
    """Check if a model is free based on its name."""
    lower = model_id.lower()
    return ":free" in lower or "-free" in lower


def filter_chat_models(
    model_list: list[dict],
    non_chat_keywords: list[str],
    free_only: bool = True,
) -> list[str]:
    """Filter model list to chat models, optionally free only."""
    if free_only:
        has_pricing = any(isinstance(m, dict) and m.get("pricing") for m in model_list)
        if has_pricing:
            free_by_api = [
                m for m in model_list
                if isinstance(m, dict) and "id" in m and is_free_model(m)
            ]
            if free_by_api:
                return [m["id"] for m in free_by_api if is_chat_model(m["id"], non_chat_keywords)]
        free_by_name = [
            m["id"] for m in model_list
            if isinstance(m, dict) and "id" in m
            and is_free_by_name(m["id"]) and is_chat_model(m["id"], non_chat_keywords)
        ]
        if free_by_name:
            return free_by_name
    return [
        m["id"] for m in model_list
        if "id" in m and isinstance(m, dict) and is_chat_model(m["id"], non_chat_keywords)
    ]
