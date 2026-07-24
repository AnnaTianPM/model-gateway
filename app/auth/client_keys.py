from __future__ import annotations

import hashlib
import json
import logging
import secrets
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import HTTPException, Request, status

from app.settings import get_settings
from app.storage.repositories import ClientKeyRepository

logger = logging.getLogger(__name__)

_KEY_PREFIX_LENGTH = 12
_RPM_WINDOW_SECONDS = 60

# In-memory RPM tracking: key_id -> deque of monotonic timestamps
_rpm_counters: dict[int, deque[float]] = defaultdict(deque)


def generate_client_key() -> str:
    """Generate a new client API key in the format ``sk-gw-client-<32 hex chars>``."""
    return f"sk-gw-client-{secrets.token_hex(16)}"


def hash_key(key: str) -> str:
    """Return the SHA-256 hex digest of the full key."""
    return hashlib.sha256(key.encode()).hexdigest()


def get_key_prefix(key: str) -> str:
    """Return the first 12 characters of the key for display purposes."""
    return key[:_KEY_PREFIX_LENGTH]


def verify_key(provided_key: str, stored_hash: str) -> bool:
    """Compare a provided key's SHA-256 hash against a stored hash.

    Uses ``secrets.compare_digest`` for constant-time comparison to
    mitigate timing attacks.
    """
    computed = hash_key(provided_key)
    return secrets.compare_digest(computed, stored_hash)


def create_client_key_sync(
    name: str,
    rpm_limit: int | None = None,
    allowed_models: list[str] | None = None,
) -> dict[str, Any]:
    """Generate a new client key and return its details (sync).

    The full ``api_key`` is only returned here — it is never retrievable
    again.
    """
    api_key = generate_client_key()
    return {
        "api_key": api_key,
        "prefix": get_key_prefix(api_key),
        "key_hash": hash_key(api_key),
        "name": name,
        "rpm_limit": rpm_limit,
        "allowed_models": allowed_models,
    }


async def create_client_key(
    name: str,
    rpm_limit: int | None = None,
    allowed_models: list[str] | None = None,
) -> dict[str, Any]:
    """Generate a new client key, persist to DB, and return details (async).

    The full ``api_key`` is only returned here — it is never retrievable
    again.
    """
    api_key = generate_client_key()
    prefix = get_key_prefix(api_key)
    kh = hash_key(api_key)

    # Parse allowed_models if it's a JSON string
    if isinstance(allowed_models, str):
        try:
            allowed_models = json.loads(allowed_models)
        except (json.JSONDecodeError, TypeError):
            allowed_models = None

    record = await ClientKeyRepository.create(
        name=name,
        key_prefix=prefix,
        key_hash=kh,
        rpm_limit=rpm_limit,
        allowed_models=allowed_models,
    )

    return {
        "api_key": api_key,
        "prefix": prefix,
        "key_hash": kh,
        "id": record.get("id"),
        "warning": "This key will not be shown again.",
    }


async def ensure_initial_client_key() -> None:
    """Create an initial client key if none exists.

    Called during application startup.
    """
    settings = get_settings()

    keys = await ClientKeyRepository.list_all()
    if keys:
        return

    logger.info("No client keys found. Creating initial key '%s'...", settings.default_client_key_name)
    result = await create_client_key(name=settings.default_client_key_name)
    logger.info("Initial client key created: %s (prefix: %s)", result["api_key"], result["prefix"])
    logger.warning("Save this key now — it will not be shown again.")


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _extract_bearer_token(request: Request) -> str | None:
    """Extract the Bearer token from the Authorization header.

    Returns ``None`` if the header is missing or not a Bearer scheme.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer ") :].strip()
        return token or None
    return None


def _check_rpm(key_id: int, rpm_limit: int | None) -> bool:
    """Check and record a request against the RPM limit.

    Uses a sliding-window counter: timestamps older than
    ``_RPM_WINDOW_SECONDS`` are evicted on each call.

    Returns ``True`` if the request is allowed, ``False`` if the
    rate limit has been exceeded.
    """
    if not rpm_limit or rpm_limit <= 0:
        return True

    now = time.monotonic()
    window = _rpm_counters[key_id]

    # Evict timestamps that fell outside the sliding window
    cutoff = now - _RPM_WINDOW_SECONDS
    while window and window[0] < cutoff:
        window.popleft()

    if len(window) >= rpm_limit:
        return False

    window.append(now)
    return True


# ------------------------------------------------------------------
# FastAPI dependencies
# ------------------------------------------------------------------


async def verify_client_key(request: Request) -> dict[str, Any]:
    """FastAPI dependency that validates the client API key.

    Extracts the Bearer token from the ``Authorization`` header, looks up
    the key hash in the database via ``ClientKeyRepository``, and returns
    the key record if the key is valid and enabled.

    Raises:
        HTTPException(401): If the token is missing, the key is not
            found, or the key is disabled.
        HTTPException(429): If the key's RPM limit has been exceeded.
    """
    token = _extract_bearer_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    key_hash = hash_key(token)
    record = await ClientKeyRepository.get_by_hash(key_hash)

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Normalise to dict in case the repository returns a Row-like object
    if not isinstance(record, dict):
        record = dict(record)

    if not record.get("enabled", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has been disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )

    key_id = record.get("id")
    rpm_limit = record.get("rpm_limit")

    if key_id is not None and not _check_rpm(key_id, rpm_limit):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )

    # Best-effort: update last_used_at — must not fail the request
    if key_id is not None:
        try:
            await ClientKeyRepository.update_last_used(key_id)
        except Exception:
            logger.debug(
                "Failed to update last_used_at for key_id=%s",
                key_id,
                exc_info=True,
            )

    return record
