"""Dashboard data freshness and source classification read model."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.config.database import DB_PATH_ENV, get_db_path
from core.config.sqlite_bootstrap import applied_schema_version, latest_migration_version
from core.telemetry.legacy_backfill import plan_legacy_telemetry_backfill


def dashboard_data_freshness_status(db_path: Path | str | None = None) -> dict[str, Any]:
    """Classify dashboard surfaces without mutating SQLite."""

    path = Path(db_path) if db_path is not None else get_db_path()
    conn = _connect_read_only(path)
    try:
        repo_frontier = latest_migration_version()
        schema_version = applied_schema_version(conn)
        table_counts = {
            table: _count(conn, table)
            for table in (
                "execution_events",
                # dashboard_attention_items, decision_records: dropped migration 139
                # (WO-AI-SPINE, AD-5) — attention/decision freshness now follows
                # execution_events (see the attention_queue section below).
                "skill_invocations",
                "hook_invocations",
                "tool_invocations",
                "workflow_invocations",
                "token_usage_records",
                "validation_results",
                # findings_current_status: dropped migration 140 (WO dff23cb0) —
                # derived from security_events at read time, not a schema object.
                "security_events",
                "research_evidence_records",
                "raw_sessions",
                "raw_skill_telemetry",
                "raw_workflow_runs",
                "hook_executions",
                "reg_projects",
                "vw_security_summary",
                "alert_rules",
                "alert_history",
            )
        }
        duckdb_token_count = _duckdb_token_count()
        sections = _section_statuses(conn, table_counts, duckdb_token_count)
        backfill_plan = plan_legacy_telemetry_backfill(path)
        generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        return {
            "model_name": "dashboard_data_freshness_status",
            "generated_at": generated_at,
            "derived_view": True,
            "primary_authority": False,
            "routing_authority": False,
            "dashboard_consumable": True,
            "db_status": {
                "schema_version": schema_version,
                "repo_migration_frontier": repo_frontier,
                "schema_is_behind_repo": schema_version < repo_frontier,
                "dream_studio_db_path_env_set": bool(os.environ.get(DB_PATH_ENV)),
                "db_path_kind": (
                    "env_override" if os.environ.get(DB_PATH_ENV) else "canonical_runtime"
                ),
            },
            "table_counts": table_counts,
            "schema_drift": _schema_drift(conn),
            "section_statuses": sections,
            "backfill_status": {
                "overall_status": backfill_plan["overall_status"],
                "dry_run": True,
                "execution_authorized": False,
                "candidate_count": sum(
                    1
                    for candidate in backfill_plan["candidates"]
                    if candidate["status"] == "candidate_requires_future_approval"
                ),
                "candidate_rows": sum(
                    int(candidate["candidate_rows"]) for candidate in backfill_plan["candidates"]
                ),
                "candidates": backfill_plan["candidates"],
            },
            "source_tables": sorted(
                [
                    table
                    for table, count in table_counts.items()
                    if count >= 0 and _exists(conn, table)
                ]
            ),
            "freshness": {
                "generated_at": generated_at,
                "stale": False,
                "staleness_basis": "query_time_snapshot",
            },
        }
    finally:
        conn.close()


def _duckdb_token_count() -> int:
    """Row count of the DuckDB aggregate_metrics.db token_usage_records view.

    WO-DBA-DROP (migration 137): token_usage_records is no longer a SQLite
    table — this is the freshness signal for the token-related sections now.
    Returns 0 (never raises) when the analytics store/view is unavailable.
    """
    try:
        from core.analytics.duckdb_store import connect_analytics

        conn = connect_analytics(read_only=True)
    except Exception:
        return 0
    try:
        return int(conn.execute("SELECT COUNT(*) FROM token_usage_records").fetchone()[0] or 0)
    except Exception:
        return 0
    finally:
        conn.close()


def _section_statuses(
    conn: sqlite3.Connection, counts: dict[str, int], duckdb_token_count: int = 0
) -> list[dict[str, Any]]:
    telemetry_component_rows = sum(
        counts[table]
        for table in (
            "skill_invocations",
            "hook_invocations",
            "tool_invocations",
            "workflow_invocations",
        )
    )
    legacy_component_rows = (
        counts["raw_skill_telemetry"] + counts["hook_executions"] + counts["raw_workflow_runs"]
    )
    session_authority_ready = _has_columns(
        conn,
        "raw_sessions",
        ["session_id", "project_id", "started_at", "ended_at", "outcome"],
    )
    security_view_ready = _has_columns(
        conn,
        "vw_security_summary",
        [
            "source_type",
            "finding_id",
            "tool",
            "severity",
            "file_path",
            "line_number",
            "message",
            "status",
            "created_at",
        ],
    )
    # alert_history dropped migration 131 (dormant) — alert authority readiness now
    # depends only on the live alert_rules table.
    alert_authority_ready = _has_columns(
        conn,
        "alert_rules",
        ["rule_id", "rule_name", "metric_path", "condition", "threshold", "severity", "enabled"],
    )
    statuses = [
        _section(
            "telemetry_overview",
            "/api/telemetry/summary",
            "fresh" if counts["execution_events"] else "empty by design",
            "Telemetry summary reads the execution spine directly.",
            ["execution_events"],
            counts["execution_events"],
            _latest(conn, "execution_events", "created_at"),
        ),
        _section(
            "attention_queue",
            "/api/telemetry/attention",
            "fresh" if counts["execution_events"] else "empty by design",
            # dashboard_attention_items dropped migration 139 (WO-AI-SPINE, AD-5) —
            # attention is now derived from execution_events (see
            # core/telemetry/read_models.py's _ATTENTION_EVENTS_VIEW_SQL).
            "Attention queue derives from execution_events (dashboard_attention_items dropped migration 139).",
            ["execution_events"],
            counts["execution_events"],
            _latest(conn, "execution_events", "created_at"),
        ),
        _section(
            "component_usage",
            "/api/telemetry/components",
            (
                "missing because telemetry is not backfilled"
                if legacy_component_rows > telemetry_component_rows
                else "fresh" if telemetry_component_rows else "empty by design"
            ),
            "Component telemetry is sparse compared with legacy component sources.",
            ["skill_invocations", "hook_invocations", "tool_invocations", "workflow_invocations"],
            telemetry_component_rows,
            _latest_any(
                conn,
                [
                    "skill_invocations",
                    "hook_invocations",
                    "tool_invocations",
                    "workflow_invocations",
                ],
                "created_at",
            ),
        ),
        _section(
            "legacy_session_metrics",
            "/api/v1/metrics/sessions",
            (
                "fresh"
                if session_authority_ready and counts["raw_sessions"]
                else (
                    "empty by design"
                    if session_authority_ready
                    else "missing because live DB schema is behind repo migrations"
                )
            ),
            "Session metrics read the repaired raw_sessions authority table; empty rows are a current empty state.",
            ["raw_sessions"],
            counts["raw_sessions"],
            _latest_any(conn, ["raw_sessions"], "started_at", "created_at"),
        ),
        _section(
            "legacy_token_metrics",
            "/api/v1/metrics/tokens",
            (
                "fresh"
                if _token_sqlite_ready(conn) and counts["token_usage_records"]
                else (
                    "empty by design"
                    if _token_sqlite_ready(conn)
                    else (
                        # WO-DBA-DROP (migration 137): token_usage_records is no
                        # longer a SQLite table by design — the DuckDB
                        # aggregate_metrics.db view is the source now, not a
                        # sign the live schema is behind repo migrations.
                        "fresh"
                        if duckdb_token_count
                        else "empty by design"
                    )
                )
            ),
            "Token metrics read the DuckDB aggregate_metrics.db token_usage_records view"
            " (derived from canonical token.consumed events); a not-yet-migrated authority"
            " with the legacy SQLite table is still read directly.",
            ["token_usage_records (DuckDB view)"],
            counts["token_usage_records"] or duckdb_token_count,
            _latest(conn, "token_usage_records", "created_at"),
        ),
        _section(
            "project_registry",
            "/api/v1/projects",
            "fresh" if counts["reg_projects"] else "empty by design",
            "Project cards read the current reg_projects registry; inactive/temp rows are excluded by the route.",
            ["reg_projects"],
            counts["reg_projects"],
            _latest_any(conn, ["reg_projects"], "last_analyzed", "created_at"),
        ),
        _section(
            "security_dashboard",
            "/api/v1/security/findings",
            (
                "fresh"
                if security_view_ready and counts["vw_security_summary"]
                else (
                    "empty by design"
                    if security_view_ready
                    else "missing because live DB schema is behind repo migrations"
                )
            ),
            "Security dashboard reads vw_security_summary, a current view over compatible security authority tables.",
            ["vw_security_summary", "security_events"],
            counts["vw_security_summary"],
            _latest(conn, "vw_security_summary", "created_at"),
        ),
        _section(
            "analytics_routes",
            "/api/v1/analytics/*",
            (
                "fresh"
                if session_authority_ready
                and (counts["raw_sessions"] or counts["token_usage_records"] or duckdb_token_count)
                else (
                    "empty by design"
                    if session_authority_ready
                    else "missing because live DB schema is behind repo migrations"
                )
            ),
            "Analytics routes read reconciled session authority (SQLite) and token authority"
            " (DuckDB aggregate_metrics.db view); return current empty states when inputs are absent.",
            ["raw_sessions", "token_usage_records (DuckDB view)"],
            counts["raw_sessions"] + counts["token_usage_records"] + duckdb_token_count,
            _latest_any(conn, ["raw_sessions", "token_usage_records"], "started_at", "created_at"),
        ),
        _section(
            "alerts_dashboard",
            "/api/v1/alerts/*",
            (
                "fresh"
                if alert_authority_ready and counts["alert_rules"]
                else (
                    "empty by design"
                    if alert_authority_ready
                    else "missing because live DB schema is behind repo migrations"
                )
            ),
            "Alert dashboard reads the alert_rules authority table; an empty table is a current "
            "empty state. (alert_history dropped migration 131 — trigger history is in-memory only.)",
            ["alert_rules", "sla_definitions"],
            counts["alert_rules"],
            _latest(conn, "alert_rules", "created_at"),
        ),
    ]
    return statuses


def _section(
    section_id: str,
    route: str,
    classification: str,
    reason: str,
    source_tables: list[str],
    row_count: int,
    latest_observed_at: str | None,
) -> dict[str, Any]:
    return {
        "section_id": section_id,
        "route": route,
        "classification": classification,
        "reason": reason,
        "source_tables": source_tables,
        "row_count": row_count,
        "latest_observed_at": latest_observed_at,
    }


def _connect_read_only(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def _exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name = ? AND type IN ('table', 'view')",
            (name,),
        ).fetchone()
        is not None
    )


def _columns(conn: sqlite3.Connection, name: str) -> set[str]:
    if not _exists(conn, name):
        return set()
    return {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{name}")')}


def _token_sqlite_ready(conn: sqlite3.Connection) -> bool:
    """True when *conn* still has a real token_usage_records table (a
    not-yet-migrated authority). Dropped by migration 137 (WO-DBA-DROP) in a
    fresh install — the DuckDB view is the source there."""
    return _has_columns(
        conn, "token_usage_records", ["input_tokens", "output_tokens", "created_at"]
    )


def _has_columns(conn: sqlite3.Connection, name: str, columns: list[str]) -> bool:
    available = _columns(conn, name)
    return all(column in available for column in columns)


def _has_any_timestamp(conn: sqlite3.Connection, name: str) -> bool:
    available = _columns(conn, name)
    return bool({"started_at", "created_at", "recorded_at"} & available)


def _count(conn: sqlite3.Connection, name: str) -> int:
    if not _exists(conn, name):
        return 0
    return int(conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] or 0)


def _latest(conn: sqlite3.Connection, name: str, column: str) -> str | None:
    if column not in _columns(conn, name):
        return None
    row = conn.execute(f'SELECT MAX("{column}") FROM "{name}"').fetchone()
    value = row[0] if row else None
    return str(value) if value is not None else None


def _latest_any(conn: sqlite3.Connection, tables: list[str], *columns: str) -> str | None:
    values: list[str] = []
    for table in tables:
        for column in columns:
            value = _latest(conn, table, column)
            if value:
                values.append(value)
    return max(values) if values else None


def _schema_drift(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    required = {
        "raw_sessions": ["started_at", "project_id", "outcome", "ended_at"],
        # token_usage_records dropped migration 137 (WO-DBA-DROP) — its absence
        # is by design (DuckDB view replaces it), not schema drift.
        "vw_security_summary": ["source_type", "finding_id", "tool", "created_at"],
        # hook_executions dropped migration 129 (DuckDB view replaces it); not schema drift.
        "alert_rules": [
            "rule_id",
            "rule_name",
            "metric_path",
            "condition",
            "threshold",
            "severity",
            "enabled",
        ],
        # alert_history dropped migration 131 (dormant feature); not schema drift.
    }
    drift = []
    for table, columns in required.items():
        if not _exists(conn, table):
            drift.append({"object": table, "issue": "missing_object", "missing": columns})
            continue
        missing = [column for column in columns if column not in _columns(conn, table)]
        if missing:
            drift.append({"object": table, "issue": "missing_columns", "missing": missing})
    return drift
