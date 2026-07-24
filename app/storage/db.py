"""Async SQLite database connection management."""

from __future__ import annotations

import logging
from pathlib import Path

import aiosqlite

from app.settings import get_settings

logger = logging.getLogger(__name__)

_connection: aiosqlite.Connection | None = None
_schema_initialized: bool = False

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    schema_version  INTEGER PRIMARY KEY,
    migration_name  TEXT NOT NULL,
    checksum        TEXT,
    applied_at      TEXT NOT NULL DEFAULT (datetime('now')),
    app_version     TEXT,
    git_commit      TEXT
);

CREATE TABLE IF NOT EXISTS deployment_history (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    deployed_at         TEXT NOT NULL DEFAULT (datetime('now')),
    app_version         TEXT,
    git_tag             TEXT,
    git_commit          TEXT,
    docker_image        TEXT,
    schema_version_before INTEGER,
    schema_version_after  INTEGER,
    backup_path         TEXT,
    status              TEXT NOT NULL DEFAULT 'success',
    notes               TEXT
);

CREATE TABLE IF NOT EXISTS providers (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL UNIQUE,
    base_url            TEXT NOT NULL,
    encrypted_api_key   TEXT,
    api_key_env_ref     TEXT,
    enabled             INTEGER NOT NULL DEFAULT 1,
    adapter_type        TEXT NOT NULL DEFAULT 'openai_compatible',
    default_headers_json TEXT,
    timeout_seconds     INTEGER NOT NULL DEFAULT 120,
    max_concurrency     INTEGER NOT NULL DEFAULT 10,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS canonical_models (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name      TEXT NOT NULL UNIQUE,
    display_name        TEXT,
    family               TEXT,
    context_length       INTEGER NOT NULL DEFAULT 32768,
    max_output_tokens    INTEGER,
    supports_stream      INTEGER NOT NULL DEFAULT 1,
    supports_tools       INTEGER NOT NULL DEFAULT 0,
    supports_json        INTEGER NOT NULL DEFAULT 0,
    supports_vision      INTEGER NOT NULL DEFAULT 0,
    supports_reasoning   INTEGER NOT NULL DEFAULT 0,
    enabled              INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS provider_routes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id         INTEGER NOT NULL REFERENCES providers(id),
    canonical_model_id  INTEGER NOT NULL REFERENCES canonical_models(id),
    upstream_model_id   TEXT NOT NULL,
    enabled             INTEGER NOT NULL DEFAULT 1,
    quota_mode          TEXT,
    quota_remaining      INTEGER,
    quota_reset_at      TEXT,
    priority_override   INTEGER,
    trust_penalty       REAL NOT NULL DEFAULT 0.0,
    notes               TEXT,
    UNIQUE (provider_id, upstream_model_id)
);

CREATE TABLE IF NOT EXISTS model_scores (
    canonical_model_id  INTEGER PRIMARY KEY REFERENCES canonical_models(id),
    general_score       INTEGER NOT NULL DEFAULT 0,
    coding_score        INTEGER NOT NULL DEFAULT 0,
    reasoning_score     INTEGER NOT NULL DEFAULT 0,
    math_score          INTEGER NOT NULL DEFAULT 0,
    writing_score       INTEGER NOT NULL DEFAULT 0,
    translation_score   INTEGER NOT NULL DEFAULT 0,
    chinese_score       INTEGER NOT NULL DEFAULT 0,
    tool_calling_score  INTEGER NOT NULL DEFAULT 0,
    vision_score        INTEGER NOT NULL DEFAULT 0,
    json_score          INTEGER NOT NULL DEFAULT 0,
    source              TEXT,
    source_url          TEXT,
    source_updated_at   TEXT,
    manually_verified   INTEGER NOT NULL DEFAULT 0,
    notes               TEXT
);

CREATE TABLE IF NOT EXISTS health_events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    route_id            INTEGER NOT NULL REFERENCES provider_routes(id),
    timestamp           REAL NOT NULL,
    source              TEXT NOT NULL,
    status              TEXT NOT NULL,
    http_status         INTEGER,
    latency_ms          REAL,
    ttft_ms             REAL,
    total_ms            REAL,
    input_tokens        INTEGER,
    output_tokens       INTEGER,
    error_code          TEXT
);
CREATE INDEX IF NOT EXISTS idx_health_events_route_time ON health_events (route_id, timestamp);

CREATE TABLE IF NOT EXISTS route_health (
    route_id                INTEGER PRIMARY KEY REFERENCES provider_routes(id),
    last_status             TEXT,
    last_checked_at         REAL,
    successes_5m            INTEGER NOT NULL DEFAULT 0,
    failures_5m             INTEGER NOT NULL DEFAULT 0,
    successes_1h            INTEGER NOT NULL DEFAULT 0,
    failures_1h             INTEGER NOT NULL DEFAULT 0,
    successes_24h           INTEGER NOT NULL DEFAULT 0,
    failures_24h            INTEGER NOT NULL DEFAULT 0,
    availability_5m         REAL NOT NULL DEFAULT 1.0,
    availability_1h         REAL NOT NULL DEFAULT 1.0,
    availability_24h        REAL NOT NULL DEFAULT 1.0,
    reliability_lcb         REAL NOT NULL DEFAULT 0.0,
    latency_p50_ms          REAL,
    latency_p95_ms          REAL,
    ttft_p50_ms             REAL,
    ttft_p95_ms             REAL,
    consecutive_failures    INTEGER NOT NULL DEFAULT 0,
    circuit_state           TEXT NOT NULL DEFAULT 'closed',
    circuit_open_until      REAL,
    cooldown_reason          TEXT
);

CREATE TABLE IF NOT EXISTS client_api_keys (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL,
    key_prefix          TEXT NOT NULL,
    key_hash            TEXT NOT NULL UNIQUE,
    enabled             INTEGER NOT NULL DEFAULT 1,
    rpm_limit           INTEGER,
    allowed_logical_models_json TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    last_used_at        TEXT
);

CREATE TABLE IF NOT EXISTS route_decisions (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id                  TEXT,
    timestamp                   REAL NOT NULL,
    client_key_id               INTEGER,
    requested_model             TEXT,
    logical_model               TEXT,
    task_type                   TEXT,
    difficulty                  TEXT,
    required_capabilities_json  TEXT,
    candidate_models_json       TEXT,
    selected_canonical_model    TEXT,
    selected_route_id           INTEGER,
    attempt_count               INTEGER NOT NULL DEFAULT 0,
    fallback_chain_json         TEXT,
    final_status                TEXT,
    total_latency_ms            REAL
);
CREATE INDEX IF NOT EXISTS idx_route_decisions_ts ON route_decisions (timestamp);
"""


def _resolve_db_path() -> Path:
    settings = get_settings()
    db_path = Path(settings.database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


async def _init_schema(conn: aiosqlite.Connection) -> None:
    """Create all tables if they do not exist."""
    global _schema_initialized
    if _schema_initialized:
        return
    await conn.executescript(_SCHEMA_SQL)
    await conn.commit()
    _schema_initialized = True
    logger.info("Database schema initialized at %s", _resolve_db_path())


async def get_db() -> aiosqlite.Connection:
    """Return a shared async SQLite connection (singleton).

    The connection uses WAL journal mode and foreign keys.
    Schema is initialised on first call.
    """
    global _connection
    if _connection is None:
        db_path = _resolve_db_path()
        _connection = await aiosqlite.connect(str(db_path))
        _connection.row_factory = aiosqlite.Row
        await _connection.execute("PRAGMA journal_mode=WAL")
        await _connection.execute("PRAGMA foreign_keys=ON")
        await _connection.execute("PRAGMA busy_timeout=5000")
        await _connection.commit()
        await _init_schema(_connection)
        logger.info("Database connection established: %s", db_path)
    return _connection


async def close_db() -> None:
    """Close the shared database connection."""
    global _connection
    if _connection is not None:
        await _connection.close()
        _connection = None
        logger.info("Database connection closed")


def reset_schema_flag() -> None:
    """Reset the schema-initialised flag (for testing)."""
    global _schema_initialized
    _schema_initialized = False
