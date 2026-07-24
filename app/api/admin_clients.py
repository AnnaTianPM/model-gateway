"""Admin API for client key management."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.admin import verify_admin

logger = logging.getLogger(__name__)

router = APIRouter()


class ClientKeyCreate(BaseModel):
    name: str
    rpm_limit: int | None = None
    allowed_logical_models: list[str] | None = None


class ClientKeyUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    rpm_limit: int | None = None
    allowed_logical_models: list[str] | None = None


@router.get("/client-keys")
async def list_client_keys(_=Depends(verify_admin)):
    """List all client API keys (without full keys)."""
    from app.storage.db import get_db
    from app.storage.repositories import ClientKeyRepository

    await get_db()
    return await ClientKeyRepository.list_all()


@router.post("/client-keys")
async def create_client_key(data: ClientKeyCreate, _=Depends(verify_admin)):
    """Create a new client API key. Full key is only returned once."""
    from app.auth.client_keys import create_client_key as _create

    return await _create(
        name=data.name,
        rpm_limit=data.rpm_limit,
        allowed_models=data.allowed_logical_models,
    )


@router.put("/client-keys/{key_id}")
async def update_client_key(key_id: int, data: ClientKeyUpdate, _=Depends(verify_admin)):
    """Update a client API key."""
    from app.storage.db import get_db
    from app.storage.repositories import ClientKeyRepository

    await get_db()
    updates = data.model_dump(exclude_unset=True)
    if "allowed_logical_models" in updates:
        allowed = updates.pop("allowed_logical_models")
        await ClientKeyRepository.update(key_id, allowed_models=allowed)
    if "enabled" in updates:
        await ClientKeyRepository.set_enabled(key_id, updates["enabled"])
    if "rpm_limit" in updates:
        await ClientKeyRepository.update(key_id, rpm_limit=updates["rpm_limit"])
    return {"ok": True}


@router.delete("/client-keys/{key_id}")
async def revoke_client_key(key_id: int, _=Depends(verify_admin)):
    """Revoke a client API key."""
    from app.storage.db import get_db
    from app.storage.repositories import ClientKeyRepository

    await get_db()
    await ClientKeyRepository.set_enabled(key_id, False)
    return {"ok": True}
