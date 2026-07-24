"""Tests for app.logging_config.mask_key and other utility functions."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ============================================================
# mask_key
# ============================================================

def test_mask_key_long():
    from app.logging_config import mask_key
    assert mask_key("nvapi-abcdefghijklmno") == "nvapi-****lmno"


def test_mask_key_short():
    from app.logging_config import mask_key
    assert mask_key("short") == "****"


def test_mask_key_empty():
    from app.logging_config import mask_key
    assert mask_key("") == ""


# ============================================================
# merge_reasoning (passthrough)
# ============================================================

def test_merge_reasoning_preserves_both():
    from app.proxy.response_normalizer import merge_reasoning
    obj = {"choices": [{"delta": {"reasoning_content": "think", "content": "hi"}}]}
    out = merge_reasoning(obj)
    assert out["choices"][0]["delta"]["content"] == "hi"
    assert out["choices"][0]["delta"]["reasoning_content"] == "think"


def test_merge_reasoning_only_reasoning():
    from app.proxy.response_normalizer import merge_reasoning
    obj = {"choices": [{"delta": {"reasoning_content": "think"}}]}
    out = merge_reasoning(obj)
    assert out["choices"][0]["delta"]["reasoning_content"] == "think"
    assert "content" not in out["choices"][0]["delta"]


def test_merge_reasoning_no_reasoning():
    from app.proxy.response_normalizer import merge_reasoning
    obj = {"choices": [{"delta": {"content": "hi"}}]}
    out = merge_reasoning(obj)
    assert out["choices"][0]["delta"]["content"] == "hi"


def test_merge_reasoning_no_choices():
    from app.proxy.response_normalizer import merge_reasoning
    obj = {"id": "x"}
    assert merge_reasoning(obj) == {"id": "x"}


# ============================================================
# compress / restore hermes
# ============================================================

def test_compress_then_restore_roundtrip():
    from app.proxy.response_normalizer import compress_hermes, restore_hermes_text
    body = {"messages": [{"role": "user", "content": "mcp_hermes_studio_use_hermes_studio_use_tool"}]}
    compressed = compress_hermes(body)
    assert "mcp_hsu_" in compressed["messages"][0]["content"]
    s = restore_hermes_text("__mcp_hsu_tool__")
    assert "mcp_hermes_studio_use_hermes_studio_use_" in s


# ============================================================
# has_image
# ============================================================

def test_has_image_with_image_url():
    from app.proxy.response_normalizer import has_image
    body = {"messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "http://x"}}]}]}
    assert has_image(body) is True


def test_has_image_without_image():
    from app.proxy.response_normalizer import has_image
    body = {"messages": [{"role": "user", "content": "hello"}]}
    assert has_image(body) is False


# ============================================================
# Circuit breaker
# ============================================================

def test_circuit_opens_after_threshold():
    from app.health.circuit_breaker import CircuitBreaker, CircuitState
    cb = CircuitBreaker()
    for _ in range(3):
        cb.record_failure(threshold=3, recovery_seconds=60)
    assert cb.state == CircuitState.OPEN


def test_circuit_resets_on_success():
    from app.health.circuit_breaker import CircuitBreaker, CircuitState
    cb = CircuitBreaker()
    cb.record_failure(threshold=3, recovery_seconds=60)
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


def test_circuit_half_open_then_closed():
    from app.health.circuit_breaker import CircuitBreaker, CircuitState
    import time
    cb = CircuitBreaker()
    for _ in range(3):
        cb.record_failure(threshold=3, recovery_seconds=60)
    assert cb.state == CircuitState.OPEN
    # Simulate recovery time passing
    cb.open_until = time.time() - 1
    assert cb.is_available() is True
    assert cb.state == CircuitState.HALF_OPEN
    # Two successes to close
    cb.record_success()
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


# ============================================================
# Reliability (Beta/Wilson)
# ============================================================

def test_beta_posterior_mean():
    from app.health.reliability import beta_posterior_mean
    # No data: (0 + 5) / (0 + 0 + 5 + 1) = 5/6
    assert abs(beta_posterior_mean(0, 0) - 5/6) < 0.01
    # All success: (10 + 5) / (10 + 0 + 5 + 1) = 15/16
    assert abs(beta_posterior_mean(10, 0) - 15/16) < 0.01


def test_wilson_lower_bound():
    from app.health.reliability import wilson_lower_bound
    # No data: 0
    assert wilson_lower_bound(0, 0) == 0.0
    # All success: high value
    lcb = wilson_lower_bound(10, 0)
    assert 0.5 < lcb <= 1.0


# ============================================================
# Canonical model normalization
# ============================================================

def test_normalize_model_name():
    from app.models.canonical import normalize_model_name
    assert normalize_model_name("deepseek-ai/deepseek-v4-flash") == "deepseek-v4-flash"
    assert normalize_model_name("DeepSeek-V4-Flash") == "deepseek-v4-flash"


def test_get_canonical_name_with_alias():
    from app.models.canonical import get_canonical_name
    aliases = {"mistralai/mistral-small-2603": "mistral-small-4-119b-2603"}
    assert get_canonical_name("mistralai/mistral-small-2603", aliases) == "mistral-small-4-119b-2603"


# ============================================================
# Error classification
# ============================================================

def test_classify_http_error():
    from app.providers.errors import classify_http_error, ErrorType
    assert classify_http_error(401) == ErrorType.AUTH_ERROR
    assert classify_http_error(403) == ErrorType.AUTH_ERROR
    assert classify_http_error(429) == ErrorType.RATE_LIMITED
    assert classify_http_error(500) == ErrorType.SERVER_ERROR
    assert classify_http_error(408) == ErrorType.TIMEOUT


def test_is_retryable():
    from app.providers.errors import ErrorType, is_retryable
    assert is_retryable(ErrorType.SERVER_ERROR) is True
    assert is_retryable(ErrorType.AUTH_ERROR) is False


def test_is_disabling():
    from app.providers.errors import ErrorType, is_disabling
    assert is_disabling(ErrorType.AUTH_ERROR) is True
    assert is_disabling(ErrorType.SERVER_ERROR) is False


# ============================================================
# Client key generation
# ============================================================

def test_generate_client_key_format():
    from app.auth.client_keys import generate_client_key
    key = generate_client_key()
    assert key.startswith("sk-gw-client-")
    assert len(key) > 20


def test_hash_key():
    from app.auth.client_keys import hash_key
    h = hash_key("sk-gw-client-test123")
    assert len(h) == 64  # SHA-256 hex


def test_verify_key():
    from app.auth.client_keys import hash_key, verify_key
    key = "sk-gw-client-test123"
    h = hash_key(key)
    assert verify_key(key, h) is True
    assert verify_key("wrong", h) is False


def test_get_key_prefix():
    from app.auth.client_keys import get_key_prefix
    assert get_key_prefix("sk-gw-client-abcdef") == "sk-gw-client"
