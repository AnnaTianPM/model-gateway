"""Admin API for provider management."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.admin import verify_admin
from app.logging_config import mask_key

logger = logging.getLogger(__name__)

router = APIRouter()


class ProviderIn(BaseModel):
    name: str
    base_url: str
    api_key: str
    models: list[str] = []
    free_only: bool = True
    adapter_type: str = "openai_compatible"
    timeout_seconds: int = 120
    max_concurrency: int = 10


class ProviderUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    models: list[str] | None = None
    free_only: bool | None = None
    enabled: bool | None = None


@router.get("/providers")
async def list_providers(_=Depends(verify_admin)):
    """List all providers with masked keys."""
    from app.storage.db import get_db
    from app.storage.repositories import ProviderRepository, ProviderRouteRepository

    await get_db()
    providers = await ProviderRepository.get_all()

    result = []
    for p in providers:
        routes = await ProviderRouteRepository.get_by_provider(p["id"])
        result.append({
            "id": p["id"],
            "name": p["name"],
            "base_url": p["base_url"],
            "api_key_masked": mask_key(p.get("encrypted_api_key", "")),
            "enabled": bool(p.get("enabled", 1)),
            "adapter_type": p.get("adapter_type", "openai_compatible"),
            "models": [r["upstream_model_id"] for r in routes if r.get("enabled", 1)],
        })
    return result


@router.post("/providers")
async def add_provider(data: ProviderIn, _=Depends(verify_admin)):
    """Add a new provider."""
    from app.storage.db import get_db
    from app.storage.repositories import ProviderRepository, ProviderRouteRepository, CanonicalModelRepository
    from app.auth.crypto import encrypt_key

    await get_db()
    encrypted = encrypt_key(data.api_key)
    provider = await ProviderRepository.add(
        name=data.name,
        base_url=data.base_url,
        encrypted_api_key=encrypted,
        adapter_type=data.adapter_type,
        timeout_seconds=data.timeout_seconds,
        max_concurrency=data.max_concurrency,
    )

    for model_id in data.models:
        canonical_name = model_id.split("/")[-1].lower()
        canonical = await CanonicalModelRepository.get_by_name(canonical_name)
        if not canonical:
            canonical = await CanonicalModelRepository.add(
                canonical_name=canonical_name,
                display_name=model_id,
                context_length=32768,
            )
        await ProviderRouteRepository.add(
            provider_id=provider["id"],
            canonical_model_id=canonical["id"],
            upstream_model_id=model_id,
        )

    return {"ok": True, "id": provider["id"]}


@router.put("/providers/{provider_id}")
async def update_provider(provider_id: int, data: ProviderUpdate, _=Depends(verify_admin)):
    """Update a provider."""
    from app.storage.db import get_db
    from app.storage.repositories import ProviderRepository
    from app.auth.crypto import encrypt_key

    await get_db()
    updates = data.model_dump(exclude_unset=True)
    if "api_key" in updates and updates["api_key"]:
        updates["encrypted_api_key"] = encrypt_key(updates.pop("api_key"))
    elif "api_key" in updates:
        del updates["api_key"]
    if updates:
        await ProviderRepository.update(provider_id, **updates)
    return {"ok": True}


@router.delete("/providers/{provider_id}")
async def delete_provider(provider_id: int, _=Depends(verify_admin)):
    """Delete a provider and its routes."""
    from app.storage.db import get_db
    from app.storage.repositories import ProviderRepository, ProviderRouteRepository

    await get_db()
    await ProviderRouteRepository.delete_by_provider(provider_id)
    await ProviderRepository.delete(provider_id)
    return {"ok": True}


@router.post("/providers/{provider_id}/verify-key")
async def verify_provider_key(provider_id: int, _=Depends(verify_admin)):
    """Verify a provider's API key."""
    from app.storage.db import get_db
    from app.storage.repositories import ProviderRepository
    from app.auth.crypto import decrypt_key
    from app.providers.openai_compatible import OpenAICompatibleProvider
    from app.providers.base import ProviderConfig
    from app.lifespan import get_http_client

    await get_db()
    provider = await ProviderRepository.get(provider_id)
    if not provider:
        raise HTTPException(404, "Provider not found")

    api_key = decrypt_key(provider["encrypted_api_key"])
    config = ProviderConfig(
        id=provider["id"], name=provider["name"],
        base_url=provider["base_url"], api_key=api_key,
    )
    adapter = OpenAICompatibleProvider(config, get_http_client())
    return await adapter.verify_key()


@router.post("/providers/{provider_id}/fetch-models")
async def fetch_models(provider_id: int, _=Depends(verify_admin)):
    """Fetch available models from a provider."""
    from app.storage.db import get_db
    from app.storage.repositories import ProviderRepository
    from app.auth.crypto import decrypt_key
    from app.providers.openai_compatible import OpenAICompatibleProvider
    from app.providers.base import ProviderConfig
    from app.lifespan import get_http_client

    await get_db()
    provider = await ProviderRepository.get(provider_id)
    if not provider:
        raise HTTPException(404, "Provider not found")

    api_key = decrypt_key(provider["encrypted_api_key"])
    config = ProviderConfig(
        id=provider["id"], name=provider["name"],
        base_url=provider["base_url"], api_key=api_key,
    )
    adapter = OpenAICompatibleProvider(config, get_http_client())
    models = await adapter.list_models()
    return {"ok": True, "models": [m.get("id", m) if isinstance(m, dict) else m for m in models]}
