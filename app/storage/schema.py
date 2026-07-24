"""Database schema definitions."""

from __future__ import annotations

PROVIDERS_SQL = """
CREATE TABLE IF NOT EXISTS providers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    base_url TEXT NOT NULL,
    encrypted_api_key TEXT,
    api_key_env_ref TEXT,
    enabled BOOLEAN DEFAULT 1,
    adapter_type TEXT DEFAULT 'openai_compatible',
    default_headers_json TEXT,
    timeout_seconds INTEGER DEFAULT 120,
    max_concurrency INTEGER DEFAULT 10,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CANONICAL_MODELS_SQL = """
CREATE TABLE IF NOT EXISTS canonical_models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT UNIQUE NOT NULL,
    display_name TEXT,
    family TEXT,
    context_length INTEGER DEFAULT 32768,
    max_output_tokens INTEGER,
    supports_stream BOOLEAN DEFAULT 1,
    supports_tools BOOLEAN DEFAULT 0,
    supports_json BOOLEAN DEFAULT 0,
    supports_vision BOOLEAN DEFAULT 0,
    supports_reasoning BOOLEAN DEFAULT 0,
    enabled BOOLEAN DEFAULT 1
);
"""

PROVIDER_ROUTES_SQL = """
CREATE TABLE IF NOT EXISTS provider_routes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id INTEGER NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    canonical_model_id INTEGER NOT NULL REFERENCES canonical_models(id) ON DELETE CASCADE,
    upstream_model_id TEXT NOT NULL,
    enabled BOOLEAN DEFAULT 1,
    quota_mode TEXT,
    quota_remaining INTEGER,
    quota_reset_at TIMESTAMP,
    priority_override INTEGER DEFAULT 0,
    trust_penalty REAL DEFAULT 0.0,
    notes TEXT,
    UNIQUE(provider_id, upstream_model_id)
);
"""

MODEL_SCORES_SQL = """
CREATE TABLE IF NOT EXISTS model_scores (
    canonical_model_id INTEGER PRIMARY KEY REFERENCES canonical_models(id) ON DELETE CASCADE,
    general_score REAL DEFAULT 0,
    coding_score REAL DEFAULT 0,
    reasoning_score REAL DEFAULT 0,
    math_score REAL DEFAULT 0,
    writing_score REAL DEFAULT 0,
    translation_score REAL DEFAULT 0,
    chinese_score REAL DEFAULT 0,
    tool_calling_score REAL DEFAULT 0,
    vision_score REAL DEFAULT 0,
    json_score REAL DEFAULT 0,
    source TEXT DEFAULT 'manual',
    source_url TEXT,
    source_updated_at TIMESTAMP,
    manually_verified BOOLEAN DEFAULT 0,
    notes TEXT
);
"""

HEALTH_EVENTS_SQL = """
CREATE TABLE IF NOT EXISTS health_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    route_id INTEGER NOT NULL REFERENCES provider_routes(id) ON DELETE CASCADE,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source TEXT NOT NULL CHECK(source IN ('probe', 'live')),
    status TEXT NOT NULL CHECK(status IN ('success', 'timeout', 'rate_limited', 'auth_error', 'server_error', 'invalid_response', 'stream_error', 'network_error', 'content_filtered', 'client_error', 'unknown')),
    http_status INTEGER,
    latency_ms REAL,
    ttft_ms REAL,
    total_ms REAL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    error_code TEXT
);
CREATE INDEX IF NOT EXISTS idx_health_events_route_time ON health_events(route_id, timestamp);
"""

ROUTE_HEALTH_SQL = """
CREATE TABLE IF NOT EXISTS route_health (
    route_id INTEGER PRIMARY KEY REFERENCES provider_routes(id) ON DELETE CASCADE,
    last_status TEXT,
    last_checked_at TIMESTAMP,
    successes_5m INTEGER DEFAULT 0,
    failures_5m INTEGER DEFAULT 0,
    successes_1h INTEGER DEFAULT 0,
    failures_1h INTEGER DEFAULT 0,
    successes_24h INTEGER DEFAULT 0,
    failures_24h INTEGER DEFAULT 0,
    availability_5m REAL DEFAULT 1.0,
    availability_1h REAL DEFAULT 1.0,
    availability_24h REAL DEFAULT 1.0,
    reliability_lcb REAL DEFAULT 1.0,
    latency_p50_ms REAL,
    latency_p95_ms REAL,
    ttft_p50_ms REAL,
    ttft_p95_ms REAL,
    consecutive_failures INTEGER DEFAULT 0,
    circuit_state TEXT DEFAULT 'closed',
    circuit_open_until TIMESTAMP,
    cooldown_reason TEXT
);
"""

CLIENT_API_KEYS_SQL = """
CREATE TABLE IF NOT EXISTS client_api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    key_prefix TEXT NOT NULL,
    key_hash TEXT UNIQUE NOT NULL,
    enabled BOOLEAN DEFAULT 1,
    rpm_limit INTEGER,
    allowed_logical_models_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP
);
"""

ROUTE_DECISIONS_SQL = """
CREATE TABLE IF NOT EXISTS route_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    client_key_id INTEGER REFERENCES client_api_keys(id),
    requested_model TEXT,
    logical_model TEXT,
    task_type TEXT,
    difficulty TEXT,
    required_capabilities_json TEXT,
    candidate_models_json TEXT,
    selected_canonical_model TEXT,
    selected_route_id INTEGER,
    attempt_count INTEGER DEFAULT 0,
    fallback_chain_json TEXT,
    final_status TEXT,
    total_latency_ms REAL
);
"""

SCHEMA_MIGRATIONS_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    schema_version INTEGER PRIMARY KEY,
    migration_name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    app_version TEXT,
    git_commit TEXT
);
"""

DEPLOYMENT_HISTORY_SQL = """
CREATE TABLE IF NOT EXISTS deployment_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deployed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    app_version TEXT,
    git_tag TEXT,
    git_commit TEXT,
    docker_image TEXT,
    schema_version_before INTEGER,
    schema_version_after INTEGER,
    backup_path TEXT,
    status TEXT NOT NULL,
    notes TEXT
);
"""

USAGE_LOG_SQL = """
CREATE TABLE IF NOT EXISTS usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    model TEXT,
    provider TEXT,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    client_key_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_usage_log_time ON usage_log(timestamp);
"""

ALL_TABLES_SQL = [
    PROVIDERS_SQL,
    CANONICAL_MODELS_SQL,
    PROVIDER_ROUTES_SQL,
    MODEL_SCORES_SQL,
    HEALTH_EVENTS_SQL,
    ROUTE_HEALTH_SQL,
    CLIENT_API_KEYS_SQL,
    ROUTE_DECISIONS_SQL,
    SCHEMA_MIGRATIONS_SQL,
    DEPLOYMENT_HISTORY_SQL,
    USAGE_LOG_SQL,
]
