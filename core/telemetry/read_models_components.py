"""WO-GF-TELEMETRY-SPLIT: read_models component usage, drilldowns, and hardening intelligence.

Extracted verbatim from core/telemetry/read_models.py (see read_models.py
facade). component_usage_summary (PUBLIC), _component_usage,
_DUCKDB_COMPONENT_EVENT_TYPES, _component_usage_from_events_fact,
_component_usage_rows, _drilldown_entry_points, _entity_drilldowns,
_process_run_drilldowns (test-imported private — see
tests/unit/test_readmodel_wiring.py), _component_drilldowns,
_component_hardening_intelligence, _source_tables_for_components.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .read_models_outcomes import _outcome_rollup
from .read_models_security import _security_rollup
from .read_models_shared import (
    COMPONENT_TABLES,
    CORE_TABLES,
    FACT_TABLES,
    ScopeFilter,
    _add_condition,
    _analytics_rows,
    _connect,
    _outcome_row_count,
    _require_tables,
    _row_count,
    _rows,
    _scope_from_rollup_row,
    _security_finding_row_count,
    _where_scope,
    _with_authority,
)
from .read_models_tokens import _token_rollup
from .read_models_validation import _validation_rollup


def component_usage_summary(
    component_type: str | None = None,
    component_id: str | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Return component usage and related outcomes across scopes."""

    with _connect(db_path) as conn:
        _require_tables(conn, (*CORE_TABLES, *FACT_TABLES))
        components = (
            {component_type: COMPONENT_TABLES[component_type]}
            if component_type in COMPONENT_TABLES
            else COMPONENT_TABLES
        )
        usage: dict[str, Any] = {}
        for component, (table, column, _label) in components.items():
            rows = _component_usage_rows(conn, component, table, column, component_id=component_id)
            usage[component] = {
                "rows": rows,
                "empty_state": f"No {component} usage recorded for the selected scope.",
                "dashboard_ready": True,
            }
        return _with_authority(
            "component_usage_summary",
            _source_tables_for_components(components),
            {
                "component_type": component_type or "all",
                "component_id": component_id,
                "usage": usage,
                "tokens": _token_rollup(
                    conn, component_type=component_type, component_id=component_id
                ),
                "validations": _validation_rollup(conn),
                "findings": _security_rollup(conn),
                "outcomes": _outcome_rollup(conn),
                "hardening_intelligence": _component_hardening_intelligence(conn, components),
            },
        )


def _component_usage(
    conn: sqlite3.Connection,
    table: str,
    component_column: str,
    *,
    scope: ScopeFilter | None = None,
    component_id: str | None = None,
) -> list[dict[str, Any]]:
    where, params = _where_scope(scope)
    if component_id:
        where, params = _add_condition(where, params, f"{component_column} = ?", component_id)
    # execution_events uses outcome_status; retain status fallback for legacy tables
    status_col = "outcome_status" if table == "execution_events" else "status"
    # exclude rows where the component ID is unset (execution_events holds all event types)
    not_null = f"{component_column} IS NOT NULL"
    where = f"{where} AND {not_null}" if where else f"WHERE {not_null}"
    return _rows(
        conn,
        f"""
        SELECT
            COALESCE(project_id, 'unknown') AS project_id,
            COALESCE(milestone_id, 'unknown') AS milestone_id,
            COALESCE(task_id, 'unknown') AS task_id,
            COALESCE(process_run_id, 'unknown') AS process_run_id,
            {component_column} AS component_id,
            COUNT(*) AS invocation_count,
            COUNT(DISTINCT project_id) AS project_count,
            COUNT(DISTINCT milestone_id) AS milestone_count,
            COUNT(DISTINCT task_id) AS task_count,
            SUM(CASE WHEN {status_col} IN ('completed', 'passed', 'recorded') THEN 1 ELSE 0 END) AS success_count,
            SUM(CASE WHEN {status_col} IN ('failed', 'error') THEN 1 ELSE 0 END) AS failure_count
        FROM {table}
        {where}
        GROUP BY project_id, milestone_id, task_id, process_run_id, {component_column}
        ORDER BY invocation_count DESC, component_id
        """,
        params,
    )


# ---------------------------------------------------------------------------
# WO-DASH-DUCKDB-PROJECTION: all-DuckDB dashboard reads. Component usage, token,
# and validation reads move off the SQLite execution_events spine and onto the
# DuckDB analytics store (aggregate_metrics.db) — the wide events_fact projection
# derived from canonical events (see core/analytics/duckdb_store.py). events_fact
# is NEVER-AUTHORITY and rebuildable; reads are read-only and fail-open to an
# empty result so a fresh install (no store yet) never 500s a dashboard route.
# ---------------------------------------------------------------------------

# Components whose usage reads the DuckDB events_fact projection. The value is the
# events_fact event_type set that represents one invocation of that component.
# Components not listed here still read the SQLite execution_events spine until
# their capture lands in canonical → events_fact (WO-HOOK-EXEC-STATS emits hook
# execution events for the hook component).
_DUCKDB_COMPONENT_EVENT_TYPES: Mapping[str, tuple[str, ...]] = {
    "workflow": ("workflow.completed", "workflow.node.completed"),
    # WO-AGENT-TELEMETRY: subagent (Task tool) invocations now emit agent.execution.*
    # carrying agent_id, so the agent component reads them from events_fact (the
    # SQLite spine never carried agent_id — it was always NULL).
    "agent": ("agent.execution.completed", "agent.execution.started", "agent.execution.failed"),
}


def _component_usage_from_events_fact(
    component_column: str,
    event_types: Sequence[str],
    *,
    scope: ScopeFilter | None = None,
    component_id: str | None = None,
) -> list[dict[str, Any]]:
    """Component usage rows from the DuckDB events_fact projection.

    Mirrors _component_usage's output shape (SQLite spine) so callers are
    source-agnostic. events_fact carries no process_run_id (canonical events do
    not), so it is reported as 'unknown' — the same honest sentinel the DuckDB
    token rollup uses.
    """
    et_placeholders = ",".join("?" for _ in event_types)
    clauses = [f"event_type IN ({et_placeholders})", f"{component_column} IS NOT NULL"]
    params: list[Any] = list(event_types)
    if scope is not None:
        for col, value in (
            ("project_id", scope.project_id),
            ("milestone_id", scope.milestone_id),
            ("task_id", scope.task_id),
        ):
            if value is not None:
                clauses.append(f"{col} = ?")
                params.append(value)
    if component_id:
        clauses.append(f"{component_column} = ?")
        params.append(component_id)
    where = "WHERE " + " AND ".join(clauses)
    return _analytics_rows(
        f"""
        SELECT
            COALESCE(project_id, 'unknown') AS project_id,
            COALESCE(milestone_id, 'unknown') AS milestone_id,
            COALESCE(task_id, 'unknown') AS task_id,
            'unknown' AS process_run_id,
            {component_column} AS component_id,
            COUNT(*) AS invocation_count,
            COUNT(DISTINCT project_id) AS project_count,
            COUNT(DISTINCT milestone_id) AS milestone_count,
            COUNT(DISTINCT task_id) AS task_count,
            SUM(CASE WHEN COALESCE(outcome, status) IN ('completed', 'passed', 'recorded')
                THEN 1 ELSE 0 END) AS success_count,
            SUM(CASE WHEN COALESCE(outcome, status) IN ('failed', 'error', 'aborted')
                THEN 1 ELSE 0 END) AS failure_count
        FROM events_fact
        {where}
        GROUP BY ALL
        ORDER BY invocation_count DESC, component_id
        """,
        params,
    )


def _component_usage_rows(
    conn: sqlite3.Connection,
    component_type: str,
    table: str,
    component_column: str,
    *,
    scope: ScopeFilter | None = None,
    component_id: str | None = None,
) -> list[dict[str, Any]]:
    """Dispatch component usage to the DuckDB events_fact projection for repointed
    components (see _DUCKDB_COMPONENT_EVENT_TYPES), else the SQLite spine."""
    event_types = _DUCKDB_COMPONENT_EVENT_TYPES.get(component_type)
    if event_types:
        return _component_usage_from_events_fact(
            component_column, event_types, scope=scope, component_id=component_id
        )
    return _component_usage(conn, table, component_column, scope=scope, component_id=component_id)


def _drilldown_entry_points(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    return {
        "projects": _entity_drilldowns(
            conn, "project", "project_id", "/api/telemetry/projects/{id}"
        ),
        "milestones": _entity_drilldowns(
            conn,
            "milestone",
            "milestone_id",
            "/api/telemetry/milestones/{id}",
            include_project=True,
        ),
        "tasks": _entity_drilldowns(
            conn,
            "task",
            "task_id",
            "/api/telemetry/tasks/{id}",
            include_project=True,
            include_milestone=True,
        ),
        "process_runs": _process_run_drilldowns(conn),
        "components": _component_drilldowns(conn),
    }


def _entity_drilldowns(
    conn: sqlite3.Connection,
    entity_type: str,
    column: str,
    path_template: str,
    *,
    include_project: bool = False,
    include_milestone: bool = False,
) -> list[dict[str, Any]]:
    rows = _rows(
        conn,
        f"""
        SELECT
            {column} AS entity_id,
            project_id,
            milestone_id,
            COUNT(*) AS event_count,
            MAX(created_at) AS latest_created_at
        FROM execution_events
        WHERE {column} IS NOT NULL AND TRIM({column}) != ''
        GROUP BY {column}, project_id, milestone_id
        ORDER BY event_count DESC, latest_created_at DESC, entity_id
        LIMIT 5
        """,
    )
    entries: list[dict[str, Any]] = []
    for row in rows:
        entity_id = str(row["entity_id"])
        api_path = path_template.replace("{id}", quote(entity_id, safe=""))
        query: list[str] = []
        if include_project and row.get("project_id"):
            query.append(f"project_id={quote(str(row['project_id']), safe='')}")
        if include_milestone and row.get("milestone_id"):
            query.append(f"milestone_id={quote(str(row['milestone_id']), safe='')}")
        if query:
            api_path = f"{api_path}?{'&'.join(query)}"
        entries.append(
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "label": entity_id,
                "api_path": api_path,
                "event_count": row["event_count"],
                "latest_created_at": row["latest_created_at"],
                "project_id": row.get("project_id"),
                "milestone_id": row.get("milestone_id"),
            }
        )
    return entries


def _process_run_drilldowns(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    # process_runs table is empty (no process.* events are emitted by the current
    # runtime). Derive process run drilldowns from execution_events.process_run_id,
    # which has real data (hook.tool_activity + skill.invoked events carry process_run_id).
    rows = _rows(
        conn,
        """
        SELECT
            process_run_id,
            MAX(project_id) AS project_id,
            MAX(milestone_id) AS milestone_id,
            MAX(task_id) AS task_id,
            COUNT(*) AS event_count,
            MAX(created_at) AS latest_created_at
        FROM execution_events
        WHERE process_run_id IS NOT NULL AND TRIM(process_run_id) != ''
        GROUP BY process_run_id
        ORDER BY latest_created_at DESC, process_run_id
        LIMIT 5
        """,
    )
    return [
        {
            "entity_type": "process_run",
            "entity_id": row["process_run_id"],
            "label": row["process_run_id"],
            "api_path": f"/api/telemetry/process-runs/{quote(str(row['process_run_id']), safe='')}",
            "status": None,
            "run_type": None,
            "project_id": row.get("project_id"),
            "milestone_id": row.get("milestone_id"),
            "task_id": row.get("task_id"),
            "latest_created_at": row.get("latest_created_at"),
        }
        for row in rows
    ]


def _component_drilldowns(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for component_type, (table, column, _label) in COMPONENT_TABLES.items():
        for row in _component_usage_rows(conn, component_type, table, column)[:3]:
            component_id = str(row["component_id"])
            entries.append(
                {
                    "entity_type": "component",
                    "component_type": component_type,
                    "entity_id": component_id,
                    "label": f"{component_type}: {component_id}",
                    "api_path": (
                        f"/api/telemetry/components/{quote(component_type, safe='')}/"
                        f"{quote(component_id, safe='')}"
                    ),
                    "invocation_count": row.get("invocation_count"),
                    "project_count": row.get("project_count"),
                    "milestone_count": row.get("milestone_count"),
                    "task_count": row.get("task_count"),
                    "project_id": row.get("project_id"),
                    "milestone_id": row.get("milestone_id"),
                    "task_id": row.get("task_id"),
                }
            )
    return sorted(
        entries, key=lambda item: (-int(item.get("invocation_count") or 0), str(item["label"]))
    )[:8]


def _component_hardening_intelligence(
    conn: sqlite3.Connection,
    components: Mapping[str, tuple[str, str, str]],
) -> dict[str, list[dict[str, Any]]]:
    intelligence: dict[str, list[dict[str, Any]]] = {}
    for component_type, (table, column, _label) in components.items():
        rows: list[dict[str, Any]] = []
        for usage in _component_usage_rows(conn, component_type, table, column)[:10]:
            scope = _scope_from_rollup_row(usage)
            token_total = sum(
                int(row.get("total_tokens") or 0)
                for row in _token_rollup(
                    conn,
                    scope=scope,
                    component_type=component_type,
                    component_id=str(usage["component_id"]),
                )
            )
            rows.append(
                {
                    "component_type": component_type,
                    "component_id": usage["component_id"],
                    "project_id": usage.get("project_id"),
                    "milestone_id": usage.get("milestone_id"),
                    "task_id": usage.get("task_id"),
                    "process_run_id": usage.get("process_run_id"),
                    "invocation_count": usage.get("invocation_count"),
                    "success_count": usage.get("success_count"),
                    "failure_count": usage.get("failure_count"),
                    "validation_count": _row_count(conn, "validation_results", scope),
                    # findings_current_status dropped migration 140 (WO dff23cb0);
                    # the security_events-derived view also lacks
                    # milestone_id/task_id/process_run_id — project-only scope.
                    "security_finding_count": _security_finding_row_count(
                        conn,
                        ScopeFilter(project_id=scope.project_id) if scope else None,
                    ),
                    "outcome_count": _outcome_row_count(conn, scope),
                    "token_total": token_total,
                    "dashboard_ready": True,
                    "derived_view": True,
                    "primary_authority": False,
                }
            )
        intelligence[component_type] = rows
    return intelligence


def _source_tables_for_components(components: Mapping[str, tuple[str, str, str]]) -> list[str]:
    # WO-DASH-DUCKDB-PROJECTION: component usage, token, and validation reads come
    # from the DuckDB analytics store (aggregate_metrics.db) — the wide events_fact
    # projection and its views — not the SQLite execution_events spine. The source
    # names reflect that DuckDB read surface so the dashboard reports its true
    # provenance. security_events stays SQLite: findings have no DuckDB projection
    # yet (a known follow-up), and are honestly named as such.
    tables = [
        "events_fact",  # DuckDB wide fact over canonical events (aggregate_metrics.db)
        "token_usage_records",  # DuckDB view over events_fact
        "security_events",  # SQLite — findings not yet DuckDB-projected
    ]
    # Components repointed to DuckDB report events_fact; any still on the SQLite
    # spine report their spine table honestly.
    for component_type, (table, _column, _label) in components.items():
        tables.append("events_fact" if component_type in _DUCKDB_COMPONENT_EVENT_TYPES else table)
    return list(dict.fromkeys(tables))
