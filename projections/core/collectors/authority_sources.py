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
            estimated_cost
        FROM token_usage_records
    """


def _has_columns(conn: sqlite3.Connection, table: str, required: set[str]) -> bool:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
        (table,),
    ).fetchone()
    if exists is None:
        return False
    columns = {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')}
    return required.issubset(columns)
