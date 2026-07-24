"""Error classification for upstream provider responses."""

from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorType(str, Enum):
    """Classification of upstream errors."""

    AUTH_ERROR = "auth_error"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    SERVER_ERROR = "server_error"
    NETWORK_ERROR = "network_error"
    INVALID_RESPONSE = "invalid_response"
    STREAM_ERROR = "stream_error"
    CONTENT_FILTERED = "content_filtered"
    CLIENT_ERROR = "client_error"
    UNKNOWN = "unknown"


def classify_http_error(status_code: int) -> ErrorType:
    """Classify an HTTP error status code."""
    if status_code in (401, 403):
        return ErrorType.AUTH_ERROR
    if status_code == 429:
        return ErrorType.RATE_LIMITED
    if status_code == 408:
        return ErrorType.TIMEOUT
    if 500 <= status_code < 600:
        return ErrorType.SERVER_ERROR
    if 400 <= status_code < 500:
        return ErrorType.CLIENT_ERROR
    return ErrorType.UNKNOWN


def classify_exception(exc: Exception) -> ErrorType:
    """Classify a network exception."""
    import httpx

    if isinstance(exc, httpx.TimeoutException):
        return ErrorType.TIMEOUT
    if isinstance(exc, httpx.ConnectError):
        return ErrorType.NETWORK_ERROR
    if isinstance(exc, httpx.RequestError):
        return ErrorType.NETWORK_ERROR
    return ErrorType.UNKNOWN


def is_content_filtered(response_body: dict[str, Any]) -> bool:
    """Check if the response indicates content filtering."""
    choices = response_body.get("choices", [])
    for choice in choices:
        finish_reason = choice.get("finish_reason", "")
        if "content_filter" in finish_reason.lower():
            return True
        message = choice.get("message", {})
        content = message.get("content", "")
        if isinstance(content, str) and "content filter" in content.lower():
            return True
    return False


def is_retryable(error_type: ErrorType) -> bool:
    """Check if an error type warrants retry/fallback."""
    return error_type in (
        ErrorType.SERVER_ERROR,
        ErrorType.TIMEOUT,
        ErrorType.NETWORK_ERROR,
        ErrorType.RATE_LIMITED,
        ErrorType.STREAM_ERROR,
    )


def is_disabling(error_type: ErrorType) -> bool:
    """Check if an error type should disable the route."""
    return error_type == ErrorType.AUTH_ERROR
