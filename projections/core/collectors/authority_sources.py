"""Dashboard collector SQL sources backed by current SQLite authority.

Legacy dashboard routes still need compact skill/token-shaped rows, but the
authority tables are the telemetry-spine records. These helpers expose a stable
subquery shape without falling back to retired raw telemetry sources.
"""

from __future__ import annotations

import sqlite3


def skill_usage_sql(conn: sqlite3.Connection) -> str | None:
    """Return a dashboard-safe skill usage subquery from skill_invocations."""

    required = {"skill_id", "status", "created_at", "metadata_json"}
    if not _has_columns(conn, "skill_invocations", required):
        return None
    return """
        SELECT
            skill_id AS skill_name,
            created_at AS invoked_at,
            CASE
                WHEN status IN ('completed', 'passed', 'recorded', 'success', 'succeeded', 'ok') THEN 1
                ELSE 0
            END AS success,
            CAST(json_extract(metadata_json, '$.execution_time_s') AS REAL) AS execution_time_s,
            json_extract(metadata_json, '$.model') AS model,
            CAST(json_extract(metadata_json, '$.input_tokens') AS INTEGER) AS input_tokens,
            CAST(json_extract(metadata_json, '$.output_tokens') AS INTEGER) AS output_tokens,
            event_id,
            project_id,
            process_run_id AS session_id
        FROM skill_invocations
        WHERE skill_id IS NOT NULL AND TRIM(skill_id) != ''
    """


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
            {confidence_expr} AS accounting_confidence
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
