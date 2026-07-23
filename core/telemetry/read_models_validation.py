"""WO-GF-TELEMETRY-SPLIT: read_models validation outcome rollups.

Extracted verbatim from core/telemetry/read_models.py (see read_models.py
facade). _validation_rollup, _validation_outcome_intelligence.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from .read_models_outcomes import _outcome_rollup
from .read_models_shared import (
    COMPONENT_TABLES,
    ScopeFilter,
    _analytics_rows,
    _none_if_unknown,
    _row_count,
    _rows,
    _security_finding_row_count,
    _where_scope,
)
from .read_models_tokens import _token_rollup


def _validation_rollup(
    conn: sqlite3.Connection, scope: ScopeFilter | None = None
) -> list[dict[str, Any]]:
    # WO-DASH-DUCKDB-PROJECTION: validation outcomes read from the DuckDB
    # events_fact projection (validation.result_recorded), not the SQLite
    # validation_results table — the all-DuckDB dashboard read path. Honestly
    # empty until WO-VALIDATION-CAPTURE lands the capture into canonical events.
    # This is NOT the validation_failures view (event.validation.failed —
    # schema-rejected events, a different metric that must not be conflated with
    # validation outcomes). conn is unused (kept for a stable call signature).
    clauses = ["event_type = 'validation.result_recorded'"]
    params: list[Any] = []
    if scope is not None:
        for col, value in (
            ("project_id", scope.project_id),
            ("milestone_id", scope.milestone_id),
            ("task_id", scope.task_id),
        ):
            if value is not None:
                clauses.append(f"{col} = ?")
                params.append(value)
    where = "WHERE " + " AND ".join(clauses)
    return _analytics_rows(
        f"""
        SELECT
            COALESCE(project_id, 'unknown') AS project_id,
            COALESCE(milestone_id, 'unknown') AS milestone_id,
            COALESCE(task_id, 'unknown') AS task_id,
            'unknown' AS process_run_id,
            json_extract_string(payload, '$.validation_type') AS component_id,
            COALESCE(status, outcome) AS status,
            COUNT(*) AS validation_count
        FROM events_fact
        {where}
        GROUP BY ALL
        ORDER BY validation_count DESC, component_id
        """,
        params,
    )


def _validation_outcome_intelligence(
    conn: sqlite3.Connection,
    scope: ScopeFilter | None = None,
) -> dict[str, Any]:
    where, params = _where_scope(scope)
    validations = _rows(
        conn,
        f"""
        SELECT
            validation_id,
            COALESCE(project_id, 'unknown') AS project_id,
            COALESCE(milestone_id, 'unknown') AS milestone_id,
            COALESCE(task_id, 'unknown') AS task_id,
            COALESCE(process_run_id, 'unknown') AS process_run_id,
            event_id,
            validation_type,
            status,
            command,
            scope AS validation_scope,
            summary,
            evidence_refs_json,
            created_at
        FROM validation_results
        {where}
        ORDER BY created_at DESC, validation_id
        """,
        params,
    )
    correlations: list[dict[str, Any]] = []
    for validation in validations:
        validation_scope = ScopeFilter(
            project_id=_none_if_unknown(validation.get("project_id")),
            milestone_id=_none_if_unknown(validation.get("milestone_id")),
            task_id=_none_if_unknown(validation.get("task_id")),
            process_run_id=_none_if_unknown(validation.get("process_run_id")),
        )
        token_rows = _token_rollup(conn, scope=validation_scope)
        token_total = sum(int(row.get("total_tokens") or 0) for row in token_rows)
        component_counts = {
            component: _row_count(conn, table, validation_scope)
            for component, (table, _column, _label) in COMPONENT_TABLES.items()
        }
        outcome_rows = _outcome_rollup(conn, validation_scope)
        correlations.append(
            {
                "validation_id": validation["validation_id"],
                "validation_type": validation["validation_type"],
                "status": validation["status"],
                "project_id": validation["project_id"],
                "milestone_id": validation["milestone_id"],
                "task_id": validation["task_id"],
                "process_run_id": validation["process_run_id"],
                # findings_current_status dropped migration 140 (WO dff23cb0);
                # the security_events-derived view also lacks
                # milestone_id/task_id/process_run_id — project-only scope.
                "security_finding_count": _security_finding_row_count(
                    conn,
                    ScopeFilter(project_id=validation_scope.project_id),
                ),
                "token_total": token_total,
                "component_counts": component_counts,
                "outcomes": outcome_rows,
                "failed_or_warning": validation["status"] in {"failed", "error", "warning"},
                "dashboard_ready": True,
                "derived_view": True,
                "primary_authority": False,
            }
        )

    failure_candidates = [
        {
            **correlation,
            "candidate_type": "validation_failure_followup_candidate",
            "requires_future_work_order": True,
            "execution_authorized": False,
        }
        for correlation in correlations
        if correlation["failed_or_warning"]
    ]
    return {
        "validations": validations,
        "correlations": correlations,
        "failure_followup_candidates": failure_candidates,
        "status_counts": _validation_rollup(conn, scope),
        "policy": {
            "derived_view": True,
            "primary_authority": False,
            "execution_authorized": False,
            "requires_future_work_order_for_fixes": True,
        },
        "empty_state": "No validation outcomes recorded for the selected scope.",
    }
