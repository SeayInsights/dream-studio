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
                "dashboard_attention_items",
                "skill_invocations",
                "hook_invocations",
                "tool_invocations",
                "workflow_invocations",
                "token_usage_records",
                "validation_results",
                "findings",
                "research_evidence_records",
                "decision_records",
                "raw_sessions",
                "raw_skill_telemetry",
                "raw_workflow_runs",
                "hook_executions",
                "reg_projects",
                "prd_documents",
                "vw_security_summary",
                "sec_sarif_findings",
                "alert_rules",
                "alert_history",
            )
        }
        sections = _section_statuses(conn, table_counts)
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


def _section_statuses(conn: sqlite3.Connection, counts: dict[str, int]) -> list[dict[str, Any]]:
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
    alert_authority_ready = _has_columns(
        conn,
        "alert_rules",
        ["rule_id", "rule_name", "metric_path", "condition", "threshold", "severity", "enabled"],
    ) and _has_columns(
        conn,
        "alert_history",
        ["alert_id", "rule_id", "triggered_at", "metric_value", "severity", "resolved_at"],
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
            "fresh" if counts["dashboard_attention_items"] else "empty by design",
            "Attention queue reads dashboard_attention_items.",
            ["dashboard_attention_items"],
            counts["dashboard_attention_items"],
            _latest(conn, "dashboard_attention_items", "created_at"),
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
                if _has_columns(
                    conn, "token_usage_records", ["input_tokens", "output_tokens", "created_at"]
                )
                and counts["token_usage_records"]
                else (
                    "empty by design"
                    if _has_columns(
                        conn, "token_usage_records", ["input_tokens", "output_tokens", "created_at"]
                    )
                    else "missing because live DB schema is behind repo migrations"
                )
            ),
            "Token metrics read current token_usage_records authority.",
            ["token_usage_records"],
            counts["token_usage_records"],
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
            "prd_list",
            "/api/prd/list",
            (
                "fresh"
                if _exists(conn, "prd_documents") and counts["prd_documents"]
                else (
                    "empty by design"
                    if _exists(conn, "prd_documents")
                    else "missing because live DB schema is behind repo migrations"
                )
            ),
            "PRD dashboard reads prd_documents authority.",
            ["prd_documents"],
            counts["prd_documents"],
            _latest(conn, "prd_documents", "created_at"),
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
            ["vw_security_summary", "findings", "sec_sarif_findings"],
            counts["vw_security_summary"],
            _latest(conn, "vw_security_summary", "created_at"),
        ),
        _section(
            "analytics_routes",
            "/api/v1/analytics/*",
            (
                "fresh"
                if session_authority_ready
                and (counts["raw_sessions"] or counts["token_usage_records"])
                else (
                    "empty by design"
                    if session_authority_ready
                    else "missing because live DB schema is behind repo migrations"
                )
            ),
            "Analytics routes read reconciled session/token authority and return current empty states when inputs are absent.",
            ["raw_sessions", "token_usage_records"],
            counts["raw_sessions"] + counts["token_usage_records"],
            _latest_any(conn, ["raw_sessions", "token_usage_records"], "started_at", "created_at"),
        ),
        _section(
            "alerts_dashboard",
            "/api/v1/alerts/*",
            (
                "fresh"
                if alert_authority_ready and (counts["alert_rules"] or counts["alert_history"])
                else (
                    "empty by design"
                    if alert_authority_ready
                    else "missing because live DB schema is behind repo migrations"
                )
            ),
            "Alert dashboard reads alert_rules and alert_history authority tables; empty tables are a current empty state.",
            ["alert_rules", "alert_history", "sla_definitions"],
            counts["alert_rules"] + counts["alert_history"],
            _latest_any(conn, ["alert_history"], "triggered_at"),
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
        "token_usage_records": ["input_tokens", "output_tokens", "created_at"],
        "prd_documents": ["prd_id", "title", "status", "created_at"],
        "vw_security_summary": ["source_type", "finding_id", "tool", "created_at"],
        "hook_executions": ["hook_exec_id", "hook_name", "started_at", "status"],
        "alert_rules": [
            "rule_id",
            "rule_name",
            "metric_path",
            "condition",
            "threshold",
            "severity",
            "enabled",
        ],
        "alert_history": ["alert_id", "rule_id", "triggered_at", "metric_value", "severity"],
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
