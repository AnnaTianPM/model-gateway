"""Data-access repositories for the model gateway."""

from __future__ import annotations

import json
import logging
import time

from app.storage.db import get_db

logger = logging.getLogger(__name__)


def _row_to_dict(row) -> dict:
    """Convert an aiosqlite.Row (or dict) to a plain dict."""
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    return dict(row)


# ---------------------------------------------------------------------------
# ProviderRepository
# ---------------------------------------------------------------------------


class ProviderRepository:
    """CRUD for the ``providers`` table."""

    @staticmethod
    async def add(
        name: str,
        base_url: str,
        encrypted_api_key: str = "",
        api_key_env_ref: str = "",
        enabled: bool = True,
        adapter_type: str = "openai_compatible",
        default_headers_json: str = "",
        timeout_seconds: int = 120,
        max_concurrency: int = 10,
    ) -> dict:
        conn = await get_db()
        cursor = await conn.execute(
            """INSERT INTO providers (name, base_url, encrypted_api_key, api_key_env_ref,
               enabled, adapter_type, default_headers_json, timeout_seconds, max_concurrency)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                name,
                base_url,
                encrypted_api_key,
                api_key_env_ref,
                1 if enabled else 0,
                adapter_type,
                default_headers_json,
                timeout_seconds,
                max_concurrency,
            ),
        )
        await conn.commit()
        return await ProviderRepository.get(cursor.lastrowid)

    @staticmethod
    async def get(provider_id: int) -> dict | None:
        conn = await get_db()
        cursor = await conn.execute("SELECT * FROM providers WHERE id = ?", (provider_id,))
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None

    @staticmethod
    async def get_all() -> list[dict]:
        conn = await get_db()
        cursor = await conn.execute("SELECT * FROM providers ORDER BY name")
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows]

    @staticmethod
    async def get_by_name(name: str) -> dict | None:
        conn = await get_db()
        cursor = await conn.execute("SELECT * FROM providers WHERE name = ?", (name,))
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None

    @staticmethod
    async def update(provider_id: int, **kwargs) -> None:
        conn = await get_db()
        sets = []
        vals = []
        for k, v in kwargs.items():
            if k == "enabled":
                v = 1 if v else 0
            sets.append(f"{k} = ?")
            vals.append(v)
        if not sets:
            return
        vals.append(provider_id)
        await conn.execute(f"UPDATE providers SET {', '.join(sets)}, updated_at = datetime('now') WHERE id = ?", vals)
        await conn.commit()

    @staticmethod
    async def delete(provider_id: int) -> None:
        conn = await get_db()
        await conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        await conn.commit()


# ---------------------------------------------------------------------------
# CanonicalModelRepository
# ---------------------------------------------------------------------------


class CanonicalModelRepository:
    """CRUD for the ``canonical_models`` table."""

    @staticmethod
    async def add(
        canonical_name: str,
        display_name: str = "",
        family: str = "",
        context_length: int = 32768,
        max_output_tokens: int | None = None,
        supports_stream: bool = True,
        supports_tools: bool = False,
        supports_json: bool = False,
        supports_vision: bool = False,
        supports_reasoning: bool = False,
        enabled: bool = True,
    ) -> dict:
        conn = await get_db()
        cursor = await conn.execute(
            """INSERT INTO canonical_models
               (canonical_name, display_name, family, context_length, max_output_tokens,
                supports_stream, supports_tools, supports_json, supports_vision,
                supports_reasoning, enabled)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                canonical_name,
                display_name,
                family,
                context_length,
                max_output_tokens,
                1 if supports_stream else 0,
                1 if supports_tools else 0,
                1 if supports_json else 0,
                1 if supports_vision else 0,
                1 if supports_reasoning else 0,
                1 if enabled else 0,
            ),
        )
        await conn.commit()
        return await CanonicalModelRepository.get(cursor.lastrowid)

    @staticmethod
    async def get(model_id: int) -> dict | None:
        conn = await get_db()
        cursor = await conn.execute("SELECT * FROM canonical_models WHERE id = ?", (model_id,))
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None

    @staticmethod
    async def get_all() -> list[dict]:
        conn = await get_db()
        cursor = await conn.execute("SELECT * FROM canonical_models ORDER BY canonical_name")
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows]

    @staticmethod
    async def get_by_name(canonical_name: str) -> dict | None:
        conn = await get_db()
        cursor = await conn.execute("SELECT * FROM canonical_models WHERE canonical_name = ?", (canonical_name,))
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None

    @staticmethod
    async def update(model_id: int, **kwargs) -> None:
        conn = await get_db()
        sets = []
        vals = []
        for k, v in kwargs.items():
            if k.startswith("supports_") or k == "enabled":
                v = 1 if v else 0
            sets.append(f"{k} = ?")
            vals.append(v)
        if not sets:
            return
        vals.append(model_id)
        await conn.execute(f"UPDATE canonical_models SET {', '.join(sets)} WHERE id = ?", vals)
        await conn.commit()


# ---------------------------------------------------------------------------
# ProviderRouteRepository
# ---------------------------------------------------------------------------


class ProviderRouteRepository:
    """CRUD for the ``provider_routes`` table."""

    @staticmethod
    async def add(
        provider_id: int,
        canonical_model_id: int,
        upstream_model_id: str,
        enabled: bool = True,
        priority_override: int = 0,
    ) -> dict:
        conn = await get_db()
        cursor = await conn.execute(
            """INSERT OR IGNORE INTO provider_routes
               (provider_id, canonical_model_id, upstream_model_id, enabled, priority_override)
               VALUES (?, ?, ?, ?, ?)""",
            (provider_id, canonical_model_id, upstream_model_id, 1 if enabled else 0, priority_override),
        )
        await conn.commit()
        return {
            "id": cursor.lastrowid,
            "provider_id": provider_id,
            "canonical_model_id": canonical_model_id,
            "upstream_model_id": upstream_model_id,
        }

    @staticmethod
    async def get(route_id: int) -> dict | None:
        conn = await get_db()
        cursor = await conn.execute("SELECT * FROM provider_routes WHERE id = ?", (route_id,))
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None

    @staticmethod
    async def get_all() -> list[dict]:
        conn = await get_db()
        cursor = await conn.execute("SELECT * FROM provider_routes")
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows]

    @staticmethod
    async def get_by_provider(provider_id: int) -> list[dict]:
        conn = await get_db()
        cursor = await conn.execute("SELECT * FROM provider_routes WHERE provider_id = ?", (provider_id,))
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows]

    @staticmethod
    async def update(route_id: int, **kwargs) -> None:
        conn = await get_db()
        sets = []
        vals = []
        for k, v in kwargs.items():
            if k == "enabled":
                v = 1 if v else 0
            sets.append(f"{k} = ?")
            vals.append(v)
        if not sets:
            return
        vals.append(route_id)
        await conn.execute(f"UPDATE provider_routes SET {', '.join(sets)} WHERE id = ?", vals)
        await conn.commit()

    @staticmethod
    async def delete(route_id: int) -> None:
        conn = await get_db()
        await conn.execute("DELETE FROM provider_routes WHERE id = ?", (route_id,))
        await conn.commit()

    @staticmethod
    async def delete_by_provider(provider_id: int) -> None:
        conn = await get_db()
        await conn.execute("DELETE FROM provider_routes WHERE provider_id = ?", (provider_id,))
        await conn.commit()


# ---------------------------------------------------------------------------
# ModelScoreRepository
# ---------------------------------------------------------------------------


class ModelScoreRepository:
    """CRUD for the ``model_scores`` table."""

    @staticmethod
    async def get(canonical_model_id: int) -> dict | None:
        conn = await get_db()
        cursor = await conn.execute("SELECT * FROM model_scores WHERE canonical_model_id = ?", (canonical_model_id,))
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None

    @staticmethod
    async def upsert(
        canonical_model_id: int,
        general_score: int = 0,
        coding_score: int = 0,
        reasoning_score: int = 0,
        math_score: int = 0,
        writing_score: int = 0,
        translation_score: int = 0,
        chinese_score: int = 0,
        tool_calling_score: int = 0,
        vision_score: int = 0,
        json_score: int = 0,
        source: str = "manual",
        notes: str = "",
    ) -> None:
        conn = await get_db()
        await conn.execute(
            """INSERT INTO model_scores
               (canonical_model_id, general_score, coding_score, reasoning_score,
                math_score, writing_score, translation_score, chinese_score,
                tool_calling_score, vision_score, json_score, source, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(canonical_model_id) DO UPDATE SET
                general_score=excluded.general_score, coding_score=excluded.coding_score,
                reasoning_score=excluded.reasoning_score, math_score=excluded.math_score,
                writing_score=excluded.writing_score, translation_score=excluded.translation_score,
                chinese_score=excluded.chinese_score, tool_calling_score=excluded.tool_calling_score,
                vision_score=excluded.vision_score, json_score=excluded.json_score,
                source=excluded.source, notes=excluded.notes""",
            (
                canonical_model_id,
                general_score,
                coding_score,
                reasoning_score,
                math_score,
                writing_score,
                translation_score,
                chinese_score,
                tool_calling_score,
                vision_score,
                json_score,
                source,
                notes,
            ),
        )
        await conn.commit()

    @staticmethod
    async def get_all() -> list[dict]:
        conn = await get_db()
        cursor = await conn.execute("SELECT * FROM model_scores")
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# HealthEventRepository
# ---------------------------------------------------------------------------


class HealthEventRepository:
    """CRUD + queries for the ``health_events`` table."""

    @staticmethod
    async def insert(event: dict) -> int:
        conn = await get_db()
        cursor = await conn.execute(
            """
            INSERT INTO health_events
                (route_id, timestamp, source, status, http_status,
                 latency_ms, ttft_ms, total_ms, input_tokens,
                 output_tokens, error_code)
            VALUES
                (:route_id, :timestamp, :source, :status, :http_status,
                 :latency_ms, :ttft_ms, :total_ms, :input_tokens,
                 :output_tokens, :error_code)
            """,
            {
                "route_id": event["route_id"],
                "timestamp": event.get("timestamp", time.time()),
                "source": event.get("source", "probe"),
                "status": event.get("status", "unknown"),
                "http_status": event.get("http_status"),
                "latency_ms": event.get("latency_ms"),
                "ttft_ms": event.get("ttft_ms"),
                "total_ms": event.get("total_ms"),
                "input_tokens": event.get("input_tokens"),
                "output_tokens": event.get("output_tokens"),
                "error_code": event.get("error_code"),
            },
        )
        await conn.commit()
        return cursor.lastrowid or 0

    @staticmethod
    async def get_by_route(route_id: int, since: float) -> list[dict]:
        conn = await get_db()
        cursor = await conn.execute(
            """
            SELECT * FROM health_events
            WHERE route_id = ? AND timestamp >= ?
            ORDER BY timestamp ASC
            """,
            (route_id, since),
        )
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows]

    @staticmethod
    async def get_recent(route_id: int, limit: int = 100) -> list[dict]:
        conn = await get_db()
        cursor = await conn.execute(
            """
            SELECT * FROM health_events
            WHERE route_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (route_id, limit),
        )
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows]

    @staticmethod
    async def count_by_route(route_id: int, since: float) -> int:
        conn = await get_db()
        cursor = await conn.execute(
            "SELECT COUNT(*) AS c FROM health_events WHERE route_id = ? AND timestamp >= ?",
            (route_id, since),
        )
        row = await cursor.fetchone()
        return int(row["c"]) if row else 0


# ---------------------------------------------------------------------------
# RouteHealthRepository
# ---------------------------------------------------------------------------


class RouteHealthRepository:
    """CRUD + queries for the ``route_health`` aggregate table."""

    @staticmethod
    async def upsert(route_id: int, health: dict) -> None:
        conn = await get_db()
        await conn.execute(
            """
            INSERT INTO route_health
                (route_id, last_status, last_checked_at,
                 successes_5m, failures_5m, successes_1h, failures_1h,
                 successes_24h, failures_24h,
                 availability_5m, availability_1h, availability_24h,
                 reliability_lcb,
                 latency_p50_ms, latency_p95_ms,
                 ttft_p50_ms, ttft_p95_ms,
                 consecutive_failures, circuit_state,
                 circuit_open_until, cooldown_reason)
            VALUES
                (:route_id, :last_status, :last_checked_at,
                 :successes_5m, :failures_5m, :successes_1h, :failures_1h,
                 :successes_24h, :failures_24h,
                 :availability_5m, :availability_1h, :availability_24h,
                 :reliability_lcb,
                 :latency_p50_ms, :latency_p95_ms,
                 :ttft_p50_ms, :ttft_p95_ms,
                 :consecutive_failures, :circuit_state,
                 :circuit_open_until, :cooldown_reason)
            ON CONFLICT(route_id) DO UPDATE SET
                last_status        = excluded.last_status,
                last_checked_at    = excluded.last_checked_at,
                successes_5m      = excluded.successes_5m,
                failures_5m       = excluded.failures_5m,
                successes_1h       = excluded.successes_1h,
                failures_1h        = excluded.failures_1h,
                successes_24h      = excluded.successes_24h,
                failures_24h       = excluded.failures_24h,
                availability_5m    = excluded.availability_5m,
                availability_1h    = excluded.availability_1h,
                availability_24h   = excluded.availability_24h,
                reliability_lcb    = excluded.reliability_lcb,
                latency_p50_ms     = excluded.latency_p50_ms,
                latency_p95_ms     = excluded.latency_p95_ms,
                ttft_p50_ms        = excluded.ttft_p50_ms,
                ttft_p95_ms        = excluded.ttft_p95_ms,
                consecutive_failures = excluded.consecutive_failures,
                circuit_state      = excluded.circuit_state,
                circuit_open_until = excluded.circuit_open_until,
                cooldown_reason    = excluded.cooldown_reason
            """,
            {
                "route_id": route_id,
                "last_status": health.get("last_status"),
                "last_checked_at": health.get("last_checked_at", time.time()),
                "successes_5m": health.get("successes_5m", 0),
                "failures_5m": health.get("failures_5m", 0),
                "successes_1h": health.get("successes_1h", 0),
                "failures_1h": health.get("failures_1h", 0),
                "successes_24h": health.get("successes_24h", 0),
                "failures_24h": health.get("failures_24h", 0),
                "availability_5m": health.get("availability_5m", 1.0),
                "availability_1h": health.get("availability_1h", 1.0),
                "availability_24h": health.get("availability_24h", 1.0),
                "reliability_lcb": health.get("reliability_lcb", 0.0),
                "latency_p50_ms": health.get("latency_p50_ms"),
                "latency_p95_ms": health.get("latency_p95_ms"),
                "ttft_p50_ms": health.get("ttft_p50_ms"),
                "ttft_p95_ms": health.get("ttft_p95_ms"),
                "consecutive_failures": health.get("consecutive_failures", 0),
                "circuit_state": health.get("circuit_state", "closed"),
                "circuit_open_until": health.get("circuit_open_until"),
                "cooldown_reason": health.get("cooldown_reason"),
            },
        )
        await conn.commit()

    @staticmethod
    async def get(route_id: int) -> dict | None:
        conn = await get_db()
        cursor = await conn.execute(
            "SELECT * FROM route_health WHERE route_id = ?",
            (route_id,),
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None

    @staticmethod
    async def get_all() -> dict[int, dict]:
        conn = await get_db()
        cursor = await conn.execute("SELECT * FROM route_health")
        rows = await cursor.fetchall()
        return {int(r["route_id"]): _row_to_dict(r) for r in rows}

    @staticmethod
    async def update_circuit(
        route_id: int,
        circuit_state: str,
        consecutive_failures: int,
        circuit_open_until: float | None = None,
        cooldown_reason: str | None = None,
    ) -> None:
        conn = await get_db()
        await conn.execute(
            """
            INSERT INTO route_health (route_id, circuit_state, consecutive_failures,
                                      circuit_open_until, cooldown_reason,
                                      last_checked_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(route_id) DO UPDATE SET
                circuit_state        = excluded.circuit_state,
                consecutive_failures = excluded.consecutive_failures,
                circuit_open_until   = excluded.circuit_open_until,
                cooldown_reason      = excluded.cooldown_reason,
                last_checked_at      = excluded.last_checked_at
            """,
            (route_id, circuit_state, consecutive_failures, circuit_open_until, cooldown_reason, time.time()),
        )
        await conn.commit()


# ---------------------------------------------------------------------------
# RouteDecisionRepository
# ---------------------------------------------------------------------------


class RouteDecisionRepository:
    """CRUD + queries for the ``route_decisions`` table."""

    @staticmethod
    async def insert(decision: dict) -> int:
        conn = await get_db()
        cursor = await conn.execute(
            """
            INSERT INTO route_decisions
                (request_id, timestamp, client_key_id, requested_model,
                 logical_model, task_type, difficulty,
                 required_capabilities_json, candidate_models_json,
                 selected_canonical_model, selected_route_id,
                 attempt_count, fallback_chain_json,
                 final_status, total_latency_ms)
            VALUES
                (:request_id, :timestamp, :client_key_id, :requested_model,
                 :logical_model, :task_type, :difficulty,
                 :required_capabilities_json, :candidate_models_json,
                 :selected_canonical_model, :selected_route_id,
                 :attempt_count, :fallback_chain_json,
                 :final_status, :total_latency_ms)
            """,
            {
                "request_id": decision.get("request_id"),
                "timestamp": decision.get("timestamp", time.time()),
                "client_key_id": decision.get("client_key_id"),
                "requested_model": decision.get("requested_model"),
                "logical_model": decision.get("logical_model"),
                "task_type": decision.get("task_type"),
                "difficulty": decision.get("difficulty"),
                "required_capabilities_json": json.dumps(decision.get("required_capabilities", []), ensure_ascii=False),
                "candidate_models_json": json.dumps(decision.get("candidate_models", []), ensure_ascii=False),
                "selected_canonical_model": decision.get("selected_canonical_model"),
                "selected_route_id": decision.get("selected_route_id"),
                "attempt_count": decision.get("attempt_count", 0),
                "fallback_chain_json": json.dumps(decision.get("fallback_chain", []), ensure_ascii=False),
                "final_status": decision.get("final_status"),
                "total_latency_ms": decision.get("total_latency_ms"),
            },
        )
        await conn.commit()
        return cursor.lastrowid or 0

    @staticmethod
    async def get_recent(limit: int = 50) -> list[dict]:
        conn = await get_db()
        cursor = await conn.execute(
            """
            SELECT * FROM route_decisions
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
        results = []
        for r in rows:
            d = _row_to_dict(r)
            d["required_capabilities"] = json.loads(d.get("required_capabilities_json") or "[]")
            d["candidate_models"] = json.loads(d.get("candidate_models_json") or "[]")
            d["fallback_chain"] = json.loads(d.get("fallback_chain_json") or "[]")
            results.append(d)
        return results


# ---------------------------------------------------------------------------
# RouteRepository (utility for loading enabled routes)
# ---------------------------------------------------------------------------


class RouteRepository:
    """Query provider routes joined with provider and canonical-model info."""

    @staticmethod
    async def get_all_enabled() -> list[dict]:
        conn = await get_db()
        cursor = await conn.execute(
            """
            SELECT
                pr.id          AS id,
                pr.provider_id  AS provider_id,
                p.name          AS provider_name,
                p.base_url      AS base_url,
                p.encrypted_api_key AS encrypted_api_key,
                p.api_key_env_ref   AS api_key_env_ref,
                pr.canonical_model_id AS canonical_model_id,
                cm.canonical_name     AS canonical_model_name,
                cm.display_name       AS display_name,
                cm.context_length     AS context_length,
                cm.supports_stream    AS supports_stream,
                cm.supports_tools     AS supports_tools,
                cm.supports_json      AS supports_json,
                cm.supports_vision    AS supports_vision,
                cm.supports_reasoning AS supports_reasoning,
                pr.upstream_model_id  AS upstream_model_id,
                pr.enabled            AS enabled,
                pr.quota_remaining    AS quota_remaining,
                pr.priority_override  AS priority_override,
                pr.trust_penalty      AS trust_penalty
            FROM provider_routes pr
            JOIN providers p ON pr.provider_id = p.id
            JOIN canonical_models cm ON pr.canonical_model_id = cm.id
            WHERE pr.enabled = 1 AND p.enabled = 1 AND cm.enabled = 1
            """
        )
        rows = await cursor.fetchall()
        routes = []
        for r in rows:
            d = _row_to_dict(r)
            d["supports_stream"] = bool(d.get("supports_stream", 0))
            d["supports_tools"] = bool(d.get("supports_tools", 0))
            d["supports_json"] = bool(d.get("supports_json", 0))
            d["supports_vision"] = bool(d.get("supports_vision", 0))
            d["supports_reasoning"] = bool(d.get("supports_reasoning", 0))
            d["enabled"] = bool(d.get("enabled", 0))
            routes.append(d)
        return routes

    @staticmethod
    async def get_by_canonical_model(canonical_name: str) -> list[dict]:
        routes = await RouteRepository.get_all_enabled()
        return [r for r in routes if r.get("canonical_model_name") == canonical_name]

    @staticmethod
    async def get_by_provider_and_model(provider_name: str, upstream_model_id: str) -> list[dict]:
        routes = await RouteRepository.get_all_enabled()
        return [
            r
            for r in routes
            if r.get("provider_name") == provider_name and r.get("upstream_model_id") == upstream_model_id
        ]


# ---------------------------------------------------------------------------
# ClientKeyRepository
# ---------------------------------------------------------------------------


class ClientKeyRepository:
    """CRUD + queries for the ``client_api_keys`` table."""

    @staticmethod
    async def get_by_hash(key_hash: str) -> dict | None:
        """Look up a client key by its SHA-256 hash."""
        conn = await get_db()
        cursor = await conn.execute(
            "SELECT * FROM client_api_keys WHERE key_hash = ?",
            (key_hash,),
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None

    @staticmethod
    async def get_by_id(key_id: int) -> dict | None:
        """Look up a client key by its primary key."""
        conn = await get_db()
        cursor = await conn.execute(
            "SELECT * FROM client_api_keys WHERE id = ?",
            (key_id,),
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None

    @staticmethod
    async def create(
        name: str,
        key_prefix: str,
        key_hash: str,
        rpm_limit: int | None = None,
        allowed_models: list[str] | None = None,
    ) -> dict:
        """Insert a new client key record.

        ``allowed_models`` is serialised to JSON for the
        ``allowed_logical_models_json`` column.
        """
        conn = await get_db()
        allowed_json = json.dumps(allowed_models, ensure_ascii=False) if allowed_models else None
        cursor = await conn.execute(
            """
            INSERT INTO client_api_keys
                (name, key_prefix, key_hash, enabled, rpm_limit,
                 allowed_logical_models_json)
            VALUES
                (?, ?, ?, 1, ?, ?)
            """,
            (name, key_prefix, key_hash, rpm_limit, allowed_json),
        )
        await conn.commit()
        return {
            "id": cursor.lastrowid or 0,
            "name": name,
            "key_prefix": key_prefix,
            "key_hash": key_hash,
            "enabled": True,
            "rpm_limit": rpm_limit,
            "allowed_logical_models_json": allowed_json,
        }

    @staticmethod
    async def update_last_used(key_id: int) -> None:
        """Set ``last_used_at`` to the current time for the given key."""
        conn = await get_db()
        await conn.execute(
            "UPDATE client_api_keys SET last_used_at = datetime('now') WHERE id = ?",
            (key_id,),
        )
        await conn.commit()

    @staticmethod
    async def list_all() -> list[dict]:
        """Return all client keys ordered by creation date (newest first).

        The ``key_hash`` column is intentionally excluded — only the
        prefix is returned for display.
        """
        conn = await get_db()
        cursor = await conn.execute(
            "SELECT id, name, key_prefix, enabled, rpm_limit, "
            "allowed_logical_models_json, created_at, last_used_at "
            "FROM client_api_keys ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows]

    @staticmethod
    async def set_enabled(key_id: int, enabled: bool) -> None:
        """Enable or disable a client key."""
        conn = await get_db()
        await conn.execute(
            "UPDATE client_api_keys SET enabled = ? WHERE id = ?",
            (1 if enabled else 0, key_id),
        )
        await conn.commit()

    @staticmethod
    async def update(
        key_id: int,
        rpm_limit: int | None = None,
        allowed_models: list[str] | None = None,
    ) -> None:
        """Update RPM limit and/or allowed models for a client key."""
        conn = await get_db()
        if rpm_limit is not None:
            await conn.execute(
                "UPDATE client_api_keys SET rpm_limit = ? WHERE id = ?",
                (rpm_limit, key_id),
            )
        if allowed_models is not None:
            await conn.execute(
                "UPDATE client_api_keys SET allowed_logical_models_json = ? WHERE id = ?",
                (json.dumps(allowed_models, ensure_ascii=False), key_id),
            )
        await conn.commit()
