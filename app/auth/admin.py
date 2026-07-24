from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import HTTPException, Request, status

from app.settings import get_settings

logger = logging.getLogger(__name__)

_ADMIN_SESSION_COOKIE = "admin_session"
_DEFAULT_ADMIN_TOKEN_PLACEHOLDER = "replace-with-a-long-random-token"


def _extract_bearer_token(request: Request) -> str | None:
    """Extract the Bearer token from the Authorization header.

    Returns ``None`` if the header is missing or not a Bearer scheme.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer ") :].strip()
        return token or None
    return None


def _is_valid_admin_token(provided: str | None) -> bool:
    """Constant-time comparison of the provided token against the configured admin token.

    Returns ``False`` if *provided* is empty, if no admin token is configured,
    or if the tokens do not match.
    """
    if not provided:
        return False

    settings = get_settings()
    expected = settings.admin_token

    if not expected:
        return False

    if expected == _DEFAULT_ADMIN_TOKEN_PLACEHOLDER:
        logger.warning(
            "ADMIN_TOKEN is still set to the default placeholder. Set ADMIN_TOKEN to a secure, long random value."
        )

    return secrets.compare_digest(provided, expected)


async def verify_admin(request: Request) -> dict[str, Any]:
    """FastAPI dependency that validates admin access.

    Checks for ``Authorization: Bearer <token>`` header first, then
    falls back to the ``X-Admin-Token`` header.

    Raises:
        HTTPException(401): If neither credential is valid.
    """
    # Primary: Authorization: Bearer <token>
    token = _extract_bearer_token(request)
    if token and _is_valid_admin_token(token):
        return {"auth_method": "bearer"}

    # Fallback: X-Admin-Token header
    admin_token_header = request.headers.get("X-Admin-Token", "").strip()
    if admin_token_header and _is_valid_admin_token(admin_token_header):
        return {"auth_method": "header"}

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing admin credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def verify_admin_or_session(request: Request) -> dict[str, Any]:
    """FastAPI dependency that validates admin access via session cookie or token.

    Checks for an admin session cookie first (for dashboard browser access),
    then falls back to Bearer token and ``X-Admin-Token`` header.

    Raises:
        HTTPException(401): If neither the cookie nor a token is valid.
    """
    # Primary: admin session cookie (for dashboard browser access)
    session_cookie = request.cookies.get(_ADMIN_SESSION_COOKIE)
    if session_cookie and _is_valid_admin_token(session_cookie):
        return {"auth_method": "session"}

    # Fallback: Authorization: Bearer <token>
    token = _extract_bearer_token(request)
    if token and _is_valid_admin_token(token):
        return {"auth_method": "bearer"}

    # Fallback: X-Admin-Token header
    admin_token_header = request.headers.get("X-Admin-Token", "").strip()
    if admin_token_header and _is_valid_admin_token(admin_token_header):
        return {"auth_method": "header"}

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing admin credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
