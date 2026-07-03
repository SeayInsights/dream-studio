"""Dashboard collector SQL sources backed by current SQLite authority.

Legacy dashboard routes still need compact skill/token-shaped rows, but the
authority tables are the telemetry-spine records. These helpers expose a stable
subquery shape without falling back to retired raw telemetry sources.
"""

from __future__ import annotations

import sqlite3
from typing import Any

# Columns the DuckDB token_usage_records view (core/analytics/duckdb_store.py)
# leaves NULL because canonical token.consumed events carry no governance
# metadata (billing mode, cost visibility, ...). Mapped to the same honest
# "unknown"/"unavailable" defaults the retired SQLite table used to write
# (WO-DBA-DROP) so downstream consumers see identical governance semantics.
_GOVERNANCE_DEFAULTS = {
    "billing_mode": "unknown",
    "token_visibility": "exact",
    "usage_source": "canonical_events",
}


def fetch_token_usage_records(since: str | None = None) -> list[dict[str, Any]] | None:
    """Fetch rows from the DuckDB aggregate_metrics.db token_usage_records view.

    WO-DBA-DROP: this is the shared row-fetch helper every token-data chokepoint
    (authority_sources.token_usage_sql, cost_analysis.api_equivalent_cost,
    read_models token rollups, usage_accounting, analytics/insights routes)
    should use once the SQLite token_usage_records table (migration 137) is
    gone. Returns column names matching the DuckDB view exactly (token_usage_id,
    project_id, milestone_id, task_id, process_run_id, agent_id, skill_id,
    workflow_id, hook_id, model_id, provider, input_tokens, output_tokens,
    cached_tokens, total_tokens, estimated_cost, purpose, created_at,
    adapter_id, billing_mode, token_visibility, cost_visibility, usage_source,
    cost_source, accounting_confidence, cache_read_tokens).

    NULL governance columns (billing_mode, token_visibility, cost_visibility,
    usage_source, cost_source, accounting_confidence) are mapped to the same
    honest-unknown defaults the retired SQLite writer used, so callers keep
    identical downstream semantics.

    Returns None — never raises — when the analytics store or view is
    unavailable (fresh install, projection runner never ran, duckdb missing).
    Callers must treat None as a harmless empty state, not an error.
    """
    try:
        from core.analytics.duckdb_store import connect_analytics

        conn = connect_analytics(read_only=True)
    except Exception:
        return None
    try:
        sql = "SELECT * FROM token_usage_records"
        params: list[str] = []
        if since:
            sql += " WHERE created_at >= ?"
            params.append(since)
        cursor = conn.execute(sql, params)
        columns = [d[0] for d in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Exception:
        return None
    finally:
        conn.close()

    out: list[dict[str, Any]] = []
    for row in rows:
        estimated_cost = row.get("estimated_cost")
        mapped = dict(row)
        for column, default in _GOVERNANCE_DEFAULTS.items():
            if mapped.get(column) is None:
                mapped[column] = default
        if mapped.get("cost_visibility") is None:
            mapped["cost_visibility"] = "estimated" if estimated_cost else "unavailable"
        if mapped.get("cost_source") is None:
            mapped["cost_source"] = "local_estimate" if estimated_cost else "unavailable"
        if mapped.get("accounting_confidence") is None:
            mapped["accounting_confidence"] = "low"
        out.append(mapped)
    return out


_SHADOW_TABLE = "_token_usage_duckdb_shadow"
_SHADOW_COLUMNS = (
    "id",
    "session_id",
    "project_id",
    "skill_name",
    "input_tokens",
    "output_tokens",
    "model",
    "recorded_at",
    "event_id",
    "total_tokens",
    "estimated_cost",
    "adapter_id",
    "provider",
    "billing_mode",
    "token_visibility",
    "cost_visibility",
    "usage_source",
    "cost_source",
    "accounting_confidence",
    "cache_read_tokens",
)


def _materialize_duckdb_token_shadow(conn: sqlite3.Connection) -> str | None:
    """Materialize current DuckDB token rows into a TEMP TABLE on *conn*.

    Every existing caller of token_usage_sql() embeds its return value as a
    SQLite subquery (``FROM ({source_sql}) token_usage ...``) executed against
    the *same* connection it passed in. Since the DuckDB view lives in a
    different database file, this fetches the rows once and writes them into a
    connection-scoped TEMP TABLE (never persisted, dropped when the connection
    closes) so every caller keeps working with zero changes — only the data
    source moved.

    Returns None (harmless — callers already treat None as "no data") when the
    analytics store has no rows.
    """
    rows = fetch_token_usage_records()
    if not rows:
        return None
    shaped = [
        (
            row.get("token_usage_id"),
            row.get("process_run_id"),
            row.get("project_id"),
            row.get("skill_id"),
            row.get("input_tokens") or 0,
            row.get("output_tokens") or 0,
            row.get("model_id"),
            row.get("created_at"),
            None,
            row.get("total_tokens") or 0,
            row.get("estimated_cost"),
            row.get("adapter_id"),
            row.get("provider"),
            row.get("billing_mode"),
            row.get("token_visibility"),
            row.get("cost_visibility"),
            row.get("usage_source"),
            row.get("cost_source"),
            row.get("accounting_confidence"),
            row.get("cache_read_tokens") or 0,
        )
        for row in rows
    ]
    conn.execute(f"DROP TABLE IF EXISTS {_SHADOW_TABLE}")
    conn.execute(f"CREATE TEMP TABLE {_SHADOW_TABLE} ({', '.join(_SHADOW_COLUMNS)})")
    conn.executemany(
        f"INSERT INTO {_SHADOW_TABLE} VALUES ({', '.join('?' for _ in _SHADOW_COLUMNS)})",
        shaped,
    )
    return f"SELECT * FROM {_SHADOW_TABLE}"


def skill_usage_sql(conn: sqlite3.Connection) -> str | None:
    """Return a dashboard-safe skill usage subquery.

    Primary: execution_events WHERE event_type='skill.invoked' — the richest
    source (skill_id direct column, 199+ rows from hook execution telemetry).
    Fallback: canonical_events WHERE event_type='skill.invoked' if
    execution_events is unavailable.

    skill_invocations was dropped in migration 106 and is no longer referenced.
    """
    # Primary: execution_events — direct skill_id column, richer dataset
    if _has_columns(
        conn, "execution_events", {"event_id", "skill_id", "outcome_status", "created_at"}
    ):
        count = conn.execute(
            "SELECT COUNT(*) FROM execution_events WHERE event_type='skill.invoked' AND skill_id IS NOT NULL AND TRIM(skill_id) != ''"
        ).fetchone()[0]
        if count > 0:
            # Derive execution_time_s by pairing execution.started ↔ execution.completed
            # rows that share the same process_run_id as the skill.invoked event.
            # Only invocations with BOTH phases present get a non-NULL duration;
            # unpaired invocations yield NULL (excluded from AVG, never fabricated).
            return """
                SELECT
                    inv.skill_id AS skill_name,
                    inv.created_at AS invoked_at,
                    CASE
                        WHEN inv.outcome_status IN ('completed', 'passed', 'recorded', 'success', 'succeeded', 'ok') THEN 1
                        ELSE 0
                    END AS success,
                    CASE
                        WHEN es.created_at IS NOT NULL AND ec.created_at IS NOT NULL
                        THEN (julianday(ec.created_at) - julianday(es.created_at)) * 86400.0
                        ELSE NULL
                    END AS execution_time_s,
                    NULL AS model,
                    NULL AS input_tokens,
                    NULL AS output_tokens,
                    inv.event_id,
                    inv.project_id,
                    inv.process_run_id AS session_id
                FROM execution_events inv
                LEFT JOIN execution_events es
                    ON es.process_run_id = inv.process_run_id
                    AND es.event_type = 'execution.started'
                LEFT JOIN execution_events ec
                    ON ec.process_run_id = inv.process_run_id
                    AND ec.event_type = 'execution.completed'
                WHERE inv.event_type = 'skill.invoked'
                  AND inv.skill_id IS NOT NULL
                  AND TRIM(inv.skill_id) != ''
            """

    # Fallback: canonical_events with skill_specifier in trace JSON
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM canonical_events WHERE event_type='skill.invoked'"
        ).fetchone()[0]
        if count > 0:
            return """
                SELECT
                    json_extract(trace, '$.skill_specifier') AS skill_name,
                    created_at AS invoked_at,
                    1 AS success,
                    NULL AS execution_time_s,
                    NULL AS model,
                    NULL AS input_tokens,
                    NULL AS output_tokens,
                    event_id,
                    json_extract(trace, '$.project_id') AS project_id,
                    NULL AS session_id
                FROM canonical_events
                WHERE event_type = 'skill.invoked'
                  AND json_extract(trace, '$.skill_specifier') IS NOT NULL
            """
    except Exception:
        pass

    return None


def token_usage_sql(conn: sqlite3.Connection) -> str | None:
    """Return a dashboard-safe token usage subquery.

    WO-DBA-DROP (migration 137): token_usage_records was retired from SQLite —
    the DuckDB aggregate_metrics.db token_usage_records view (derived from
    canonical token.consumed events via events_fact) is the sole source now.

    Two branches:
      1. If *conn* still has a real token_usage_records table (a not-yet-
         migrated authority, or a test fixture that builds one directly) —
         read it exactly as before. This branch is dead in any authority that
         has run migration 137, but stays correct and harmless for anything
         that hasn't.
      2. Otherwise, materialize the current DuckDB rows into a connection-
         scoped SQLite TEMP TABLE and return a SELECT over it, so every caller
         that embeds this function's return value as a subquery against *conn*
         (token_collector.py, model_collector.py,
         projections/api/routes/metrics.py,
         projections/api/routes/intelligence.py) keeps working unchanged.

    Returns None (harmless empty state, never an error) when neither source has
    data.
    """

    required = {
        "token_usage_id",
        "project_id",
        "process_run_id",
        "skill_id",
        "input_tokens",
        "output_tokens",
        "model_id",
        "created_at",
        "total_tokens",
        "estimated_cost",
    }
    if _has_columns(conn, "token_usage_records", required):
        columns = _columns(conn, "token_usage_records")
        adapter_expr = _column_or_literal(columns, "adapter_id", "NULL")
        provider_expr = _column_or_literal(columns, "provider", "NULL")
        billing_expr = _column_or_literal(columns, "billing_mode", "'unknown'")
        token_visibility_expr = _column_or_literal(columns, "token_visibility", "'exact'")
        cost_visibility_expr = _column_or_literal(columns, "cost_visibility", "'unknown'")
        usage_source_expr = _column_or_literal(columns, "usage_source", "'local_telemetry'")
        cost_source_expr = _column_or_literal(columns, "cost_source", "'unknown'")
        confidence_expr = _column_or_literal(columns, "accounting_confidence", "'medium'")
        cache_read_expr = _column_or_literal(columns, "cache_read_tokens", "0")

        primary_count = conn.execute("SELECT COUNT(*) FROM token_usage_records").fetchone()[0]
        if primary_count > 0:
            return f"""
                SELECT
                    token_usage_id AS id,
                    process_run_id AS session_id,
                    project_id,
                    skill_id AS skill_name,
                    input_tokens,
                    output_tokens,
                    model_id AS model,
                    created_at AS recorded_at,
                    NULL AS event_id,
                    total_tokens,
                    estimated_cost,
                    {adapter_expr} AS adapter_id,
                    {provider_expr} AS provider,
                    {billing_expr} AS billing_mode,
                    {token_visibility_expr} AS token_visibility,
                    {cost_visibility_expr} AS cost_visibility,
                    {usage_source_expr} AS usage_source,
                    {cost_source_expr} AS cost_source,
                    {confidence_expr} AS accounting_confidence,
                    {cache_read_expr} AS cache_read_tokens
                FROM token_usage_records
            """

        # Fallback: token_usage_records exists but is empty — project from
        # ai_canonical_events. token.consumed events carry per-tool-invocation
        # usage from the PostToolUse hook. Suppressed once token_usage_records
        # is populated to prevent double-counting.
        try:
            canonical_count = conn.execute(
                "SELECT COUNT(*) FROM ai_canonical_events"
                " WHERE event_type='token.consumed'"
                " AND json_extract(payload, '$.input_tokens') IS NOT NULL"
            ).fetchone()[0]
            if canonical_count > 0:
                return """
                    SELECT
                        event_id AS id,
                        session_id AS session_id,
                        json_extract(trace, '$.project_id') AS project_id,
                        NULL AS skill_name,
                        CAST(COALESCE(json_extract(payload, '$.input_tokens'), 0) AS INTEGER)
                            AS input_tokens,
                        CAST(COALESCE(json_extract(payload, '$.output_tokens'), 0) AS INTEGER)
                            AS output_tokens,
                        COALESCE(model_id, json_extract(payload, '$.model')) AS model,
                        received_at AS recorded_at,
                        event_id AS event_id,
                        CAST(
                            COALESCE(json_extract(payload, '$.input_tokens'), 0)
                            + COALESCE(json_extract(payload, '$.output_tokens'), 0)
                            AS INTEGER
                        ) AS total_tokens,
                        NULL AS estimated_cost,
                        NULL AS adapter_id,
                        NULL AS provider,
                        'unknown' AS billing_mode,
                        'exact' AS token_visibility,
                        'unknown' AS cost_visibility,
                        'canonical_events' AS usage_source,
                        'unknown' AS cost_source,
                        'low' AS accounting_confidence,
                        CAST(
                            COALESCE(json_extract(payload, '$.cache_read_input_tokens'), 0)
                            AS INTEGER
                        ) AS cache_read_tokens
                    FROM ai_canonical_events
                    WHERE event_type = 'token.consumed'
                      AND json_extract(payload, '$.input_tokens') IS NOT NULL
                """
        except Exception:
            pass

        # token_usage_records exists but is empty and no canonical fallback available.
        return f"""
            SELECT
                token_usage_id AS id,
                process_run_id AS session_id,
                project_id,
                skill_id AS skill_name,
                input_tokens,
                output_tokens,
                model_id AS model,
                created_at AS recorded_at,
                NULL AS event_id,
                total_tokens,
                estimated_cost,
                {adapter_expr} AS adapter_id,
                {provider_expr} AS provider,
                {billing_expr} AS billing_mode,
                {token_visibility_expr} AS token_visibility,
                {cost_visibility_expr} AS cost_visibility,
                {usage_source_expr} AS usage_source,
                {cost_source_expr} AS cost_source,
                {confidence_expr} AS accounting_confidence,
                {cache_read_expr} AS cache_read_tokens
            FROM token_usage_records
        """

    # No SQLite token_usage_records table at all (the post-migration-137
    # reality) — DuckDB is the sole source. Never raises: an unavailable
    # analytics store just means no token data this call.
    try:
        return _materialize_duckdb_token_shadow(conn)
    except Exception:
        return None


def _has_columns(conn: sqlite3.Connection, table: str, required: set[str]) -> bool:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
        (table,),
    ).fetchone()
    if exists is None:
        return False
    return required.issubset(_columns(conn, table))


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _column_or_literal(columns: set[str], column: str, literal: str) -> str:
    return column if column in columns else literal
