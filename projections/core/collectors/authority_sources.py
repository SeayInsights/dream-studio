"""Dashboard collector SQL sources backed by current SQLite authority.

Legacy dashboard routes still need compact skill/token-shaped rows, but the
authority tables are the telemetry-spine records. These helpers expose a stable
subquery shape without falling back to retired raw telemetry sources.
"""

from __future__ import annotations

import sqlite3


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
            return """
                SELECT
                    skill_id AS skill_name,
                    created_at AS invoked_at,
                    CASE
                        WHEN outcome_status IN ('completed', 'passed', 'recorded', 'success', 'succeeded', 'ok') THEN 1
                        ELSE 0
                    END AS success,
                    NULL AS execution_time_s,
                    NULL AS model,
                    NULL AS input_tokens,
                    NULL AS output_tokens,
                    event_id,
                    project_id,
                    process_run_id AS session_id
                FROM execution_events
                WHERE event_type = 'skill.invoked'
                  AND skill_id IS NOT NULL
                  AND TRIM(skill_id) != ''
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
    """Return a dashboard-safe token usage subquery from token_usage_records."""

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
    if not _has_columns(conn, "token_usage_records", required):
        return None
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
    return """
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
    """.format(
        adapter_expr=adapter_expr,
        provider_expr=provider_expr,
        billing_expr=billing_expr,
        token_visibility_expr=token_visibility_expr,
        cost_visibility_expr=cost_visibility_expr,
        usage_source_expr=usage_source_expr,
        cost_source_expr=cost_source_expr,
        confidence_expr=confidence_expr,
        cache_read_expr=cache_read_expr,
    )


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
