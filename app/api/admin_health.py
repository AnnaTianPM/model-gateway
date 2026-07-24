"""Admin API for health monitoring."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.auth.admin import verify_admin

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def get_health(_=Depends(verify_admin)):
    """Get aggregated health status for all routes."""
    from app.storage.db import get_db
    from app.storage.repositories import RouteHealthRepository, RouteRepository, ProviderRepository

    await get_db()
    all_health = await RouteHealthRepository.get_all()
    all_routes = await RouteRepository.get_all_enabled()
    providers = {p["id"]: p for p in await ProviderRepository.get_all()}

    result = []
    for h in all_health.values():
        route_id = h.get("route_id")
        route = next((r for r in all_routes if r["id"] == route_id), None)
        if not route:
            continue
        provider = providers.get(route.get("provider_id"), {})
        result.append({
            "provider": provider.get("name", "unknown"),
            "upstream_model_id": route.get("upstream_model_id", ""),
            "last_status": h.get("last_status", "unknown"),
            "availability_5m": h.get("availability_5m", 0),
            "availability_1h": h.get("availability_1h", 0),
            "availability_24h": h.get("availability_24h", 0),
            "reliability_lcb": h.get("reliability_lcb", 0),
            "latency_p95_ms": h.get("latency_p95_ms"),
            "ttft_p95_ms": h.get("ttft_p95_ms"),
            "consecutive_failures": h.get("consecutive_failures", 0),
            "circuit_state": h.get("circuit_state", "closed"),
        })
    result.sort(key=lambda x: (-(x.get("availability_5m") or 0), x.get("latency_p95_ms") or 99999))
    return result


@router.post("/health/check/{route_id}")
async def manual_check(route_id: int, _=Depends(verify_admin)):
    """Manually trigger a health check for a specific route."""
    from app.storage.db import get_db
    from app.storage.repositories import RouteRepository, ProviderRepository
    from app.auth.crypto import decrypt_key
    from app.health.probes import probe_route
    from app.lifespan import get_http_client

    await get_db()
    routes = await RouteRepository.get_all_enabled()
    route = next((r for r in routes if r["id"] == route_id), None)
    if not route:
        raise HTTPException(404, "Route not found")

    provider = await ProviderRepository.get(route["provider_id"])
    if not provider:
        raise HTTPException(404, "Provider not found")

    api_key = decrypt_key(provider["encrypted_api_key"])
    return await probe_route(
        base_url=provider["base_url"],
        api_key=api_key,
        model=route["upstream_model_id"],
        http_client=get_http_client(),
    )


@router.post("/health/check/all")
async def check_all(_=Depends(verify_admin)):
    """Trigger health check for all enabled routes."""
    from app.storage.db import get_db
    from app.storage.repositories import RouteRepository, ProviderRepository
    from app.auth.crypto import decrypt_key
    from app.health.probes import probe_route
    from app.lifespan import get_http_client
    import asyncio

    await get_db()
    routes = await RouteRepository.get_all_enabled()
    providers = {p["id"]: p for p in await ProviderRepository.get_all()}
    http_client = get_http_client()

    async def check_one(route):
        provider = providers.get(route["provider_id"])
        if not provider or not provider.get("enabled"):
            return None
        api_key = decrypt_key(provider["encrypted_api_key"])
        return await probe_route(
            base_url=provider["base_url"], api_key=api_key,
            model=route["upstream_model_id"], http_client=http_client,
        )

    results = await asyncio.gather(*[check_one(r) for r in routes], return_exceptions=True)
    return [r for r in results if r and not isinstance(r, Exception)]
