"""Derived dashboard read models for the execution telemetry spine.

This module reads migration-037 telemetry tables and returns JSON-friendly
models for dashboard/reporting callers. The read models are intentionally
derived views: they do not mutate SQLite and they are not workflow authority.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from core.config.database import get_db_path
from core.shared_intelligence.usage_accounting import adapter_usage_accounting_summary
from core.telemetry.execution_spine import dashboard_module_declarations

CORE_TABLES: tuple[str, ...] = (
    "execution_events",
    # process_runs: empty in production (no process.* events emitted); removed from
    # core required tables — summaries derive from execution_events.process_run_id.
    # route_decision_records: dropped migration 131 (dead writer emit_route_decision())
    # dashboard_attention_items: dropped migration 139 (WO-AI-SPINE, AD-5) — attention
    # is now derived from execution_events (see _ATTENTION_EVENTS_VIEW_SQL below).
)

FACT_TABLES: tuple[str, ...] = (
    # token_usage_records: dropped migration 137 (WO-DBA-DROP) — no longer a
    # SQLite table in a fresh install, so it is not a required-table gate
    # input. _token_rollup/_token_cost_intelligence read the DuckDB
    # aggregate_metrics.db token_usage_records view instead (with a legacy
    # SQLite-table branch kept for any not-yet-migrated authority).
    "ai_adapter_accounting_profiles",
    "ai_usage_operational_records",  # KEPT: live writer analytics_ingestion.ingest_analytics_payload()
    "findings_current_status",  # findings retired in migration 112 → findings_current_status
    "validation_results",
    "research_evidence_records",
    # decision_records: dropped migration 139 (WO-AI-SPINE, AD-5) — decisions are
    # now derived from execution_events (see _DECISION_EVENTS_VIEW_SQL below).
    # blocker_resolution_records: dropped migration 130 (aspirational, 0 rows, no live writer)
    # artifact_records: dropped migration 130 (aspirational, 0 rows, no production writer)
    # authority_projection_records: dropped migration 130 (aspirational, 0 rows, no live writer)
    # outcome_records: dropped migration 139 (WO-AI-SPINE, AD-5) — outcomes are now
    # derived from execution_events (see _OUTCOME_EVENTS_VIEW_SQL below).
)

# ---------------------------------------------------------------------------
# WO-AI-SPINE (migration 139, AD-5): decision_records, outcome_records, and
# dashboard_attention_items were dropped — they were per-type fact tables that
# duplicated the execution_events row every writer in core/telemetry/emitters.py
# already wrote (0/2/0 production rows). The three SQL fragments below project
# execution_events rows back into the retired tables' column shapes so every
# read model below keeps its original dict/list shape. Fields that were never
# persisted anywhere except the dropped tables (decision selected_option/
# rationale, outcome/attention summary, true attention title/severity) are
# honestly NULL/best-effort derived — see each fragment's comment.
# ---------------------------------------------------------------------------

# decision_type is recovered from event_name, which emit_decision_record()
# writes as f"Decision: {decision_type}" ("Decision: " is 10 characters, so the
# type starts at position 11). decision_status is outcome_status verbatim.
# selected_option and rationale were only ever persisted in decision_records —
# they are not recoverable from execution_events and are honestly NULL here.
_DECISION_EVENTS_VIEW_SQL = """
    SELECT
        event_id AS decision_id,
        project_id,
        milestone_id,
        task_id,
        process_run_id,
        event_id,
        SUBSTR(event_name, 11) AS decision_type,
        outcome_status AS decision_status,
        NULL AS selected_option,
        NULL AS rationale,
        source_refs_json,
        evidence_refs_json,
        created_at
    FROM execution_events
    WHERE event_type = 'decision.recorded'
"""

# outcome_type maps 1:1 from event_type — these are exactly the three event
# types emit_validation_result / emit_workflow_invocation / emit_decision_record
# write, matching outcome_records' historical outcome_type values verbatim.
# summary was only ever persisted in outcome_records and is honestly NULL here.
_OUTCOME_EVENTS_VIEW_SQL = """
    SELECT
        event_id AS outcome_id,
        project_id,
        milestone_id,
        task_id,
        process_run_id,
        event_id,
        CASE event_type
            WHEN 'validation.result_recorded' THEN 'validation'
            WHEN 'workflow.invocation_recorded' THEN 'workflow'
            WHEN 'decision.recorded' THEN 'decision'
        END AS outcome_type,
        outcome_status,
        NULL AS summary,
        evidence_refs_json,
        created_at
    FROM execution_events
    WHERE event_type IN (
        'validation.result_recorded', 'workflow.invocation_recorded', 'decision.recorded'
    )
"""

# dashboard_attention_items was written conditionally (only on bad outcomes) by
# emit_validation_result, emit_workflow_invocation, and emit_security_finding.
# The condition is approximated here from outcome_status alone (the per-item
# fail/error/warning counts and true finding severity were never persisted on
# execution_events, only on the dropped table / are unavailable at read time).
# Security findings default to "warning" severity since true severity isn't on
# execution_events (only the finding's status is) — an open/unresolved finding
# still deserves operator attention even without its original severity.
# research.evidence_recorded and decision.recorded attention triggers depended
# entirely on boolean flags (operator_verification_required, prompt_required,
# operator_required, approval_required) that were never persisted on
# execution_events either; those two event types are intentionally excluded
# here rather than over- or under-including them. research_evidence_records
# still carries operator_verification_required directly for callers that need it.
_ATTENTION_EVENTS_VIEW_SQL = """
    SELECT
        event_id AS attention_id,
        project_id,
        milestone_id,
        task_id,
        process_run_id,
        event_id,
        CASE
            WHEN event_type = 'validation.result_recorded' AND outcome_status = 'warning'
                THEN 'validation_warning'
            WHEN event_type = 'validation.result_recorded' THEN 'validation_failure'
            WHEN event_type = 'workflow.invocation_recorded' THEN 'workflow_status_attention'
            WHEN event_type = 'security.finding_recorded' THEN 'security_finding'
        END AS attention_type,
        CASE
            WHEN event_type = 'security.finding_recorded' THEN 'warning'
            WHEN outcome_status = 'error' THEN 'high'
            WHEN outcome_status IN ('failed', 'warning') THEN 'warning'
            ELSE 'info'
        END AS severity,
        event_name AS title,
        NULL AS summary,
        1 AS action_required,
        0 AS operator_action_required,
        0 AS prompt_required,
        'open' AS status,
        source_refs_json,
        evidence_refs_json,
        created_at,
        created_at AS updated_at
    FROM execution_events
    WHERE (
        event_type IN ('validation.result_recorded', 'workflow.invocation_recorded')
        AND outcome_status IN ('failed', 'error', 'warning')
    )
    OR (
        event_type = 'security.finding_recorded'
        AND outcome_status IN ('open', 'unresolved')
    )
"""

COMPONENT_TABLES: Mapping[str, tuple[str, str, str]] = {
    "agent": ("execution_events", "agent_id", "Agent Analytics"),
    "skill": ("execution_events", "skill_id", "Skill Analytics"),
    "workflow": ("execution_events", "workflow_id", "Workflow Analytics"),
    "hook": ("execution_events", "hook_id", "Hook Analytics"),
    "tool": ("execution_events", "tool_id", "Tool Analytics"),
}

MODULE_SEGMENTS: Mapping[str, tuple[str, ...]] = {
    "security_only": ("security_analytics",),
    "token_only": ("token_analytics",),
    "component_only": (
        "agent_analytics",
        "skill_analytics",
        "workflow_analytics",
        "hook_analytics",
        "tool_analytics",
    ),
    "validation_only": ("validation_analytics",),
    "research_decision_only": ("research_decision_analytics",),
    # artifact_only removed: artifact_analytics module dropped in migration 130
    "route_attention_only": ("route_milestone_analytics",),
}


@dataclass(frozen=True)
class ScopeFilter:
    project_id: str | None = None
    milestone_id: str | None = None
    task_id: str | None = None
    process_run_id: str | None = None


def dashboard_module_read_models() -> list[dict[str, Any]]:
    """Return modular dashboard read-model declarations with authority metadata."""

    modules: list[dict[str, Any]] = []
    for module in dashboard_module_declarations():
        source_tables = list(module["source_tables"])
        modules.append(
            {
                "module_id": module["module_id"],
                "module_name": module["module_name"],
                "module_type": module["module_type"],
                "enabled": True,
                "source_tables": source_tables,
                "required_core_tables": list(CORE_TABLES),
                "optional_tables": [
                    table for table in module.get("owns_tables", []) if table not in source_tables
                ],
                "empty_state": module["empty_state"],
                "dashboard_cards": list(module["dashboard_cards"]),
                "drilldown_paths": list(module["drilldown_paths"]),
                "validation_requirements": [
                    "source_tables_exist",
                    "query_returns_empty_state_when_no_rows",
                    "derived_view_metadata_present",
                ],
                "derived_view": True,
                "primary_authority": False,
                "authority_note": "Dashboard modules are derived views over SQLite telemetry facts.",
            }
        )
    modules.append(
        {
            "module_id": "tool_analytics",
            "module_name": "Tool Analytics",
            "module_type": "dashboard_projection",
            "enabled": True,
            "source_tables": ["execution_events"],
            "required_core_tables": list(CORE_TABLES),
            "optional_tables": [],
            "empty_state": "No tool invocations recorded for the selected scope.",
            "dashboard_cards": ["tool_usage", "tool_outcomes"],
            "drilldown_paths": ["project", "milestone", "task", "process_run", "tool"],
            "validation_requirements": [
                "source_tables_exist",
                "query_returns_empty_state_when_no_rows",
                "derived_view_metadata_present",
            ],
            "derived_view": True,
            "primary_authority": False,
            "authority_note": "Dashboard modules are derived views over SQLite telemetry facts.",
        }
    )
    return modules


def dashboard_module_segments(segment: str | None = None) -> dict[str, Any]:
    """Return dashboard modules grouped for independently enabled surfaces."""

    modules = dashboard_module_read_models()
    by_id = {module["module_id"]: module for module in modules}
    segments: dict[str, Any] = {}
    for segment_id, module_ids in MODULE_SEGMENTS.items():
        segment_modules = [by_id[module_id] for module_id in module_ids if module_id in by_id]
        segments[segment_id] = {
            "segment_id": segment_id,
            "enabled": True,
            "module_ids": [module["module_id"] for module in segment_modules],
            "modules": segment_modules,
            "empty_state": "No enabled modules or telemetry facts for this segment.",
            "derived_view": True,
            "primary_authority": False,
        }
    selected = segments.get(segment) if segment else None
    return {
        "model_name": "dashboard_module_segments",
        "segments": segments,
        "active_segment": segment,
        "modules": selected["modules"] if selected else modules,
        "segment_available": selected is not None if segment else True,
        "derived_view": True,
        "primary_authority": False,
        "source_tables": [],
        "empty_state_behavior": "Segments return enabled module declarations and empty states independently.",
    }


def global_telemetry_summary(db_path: Path | str | None = None) -> dict[str, Any]:
    """Summarize global telemetry across projects, milestones, tasks, and components."""

    with _connect(db_path) as conn:
        _require_tables(conn, (*CORE_TABLES, *FACT_TABLES))
        source_tables = list(dict.fromkeys((*CORE_TABLES, *FACT_TABLES)))
        return _with_authority(
            "global_telemetry_summary",
            source_tables,
            {
                "scope": "global",
                "entity_counts": _entity_counts(conn),
                "table_counts": _table_counts(conn, source_tables),
                "component_usage": {
                    component: _component_usage(conn, table, column)
                    for component, (table, column, _label) in COMPONENT_TABLES.items()
                },
                "token_usage": _token_rollup(conn),
                "token_cost_intelligence": _token_cost_intelligence(conn),
                "ai_usage_accounting": adapter_usage_accounting_summary(conn),
                "findings": _security_rollup(conn),
                "security_remediation_intelligence": _security_remediation_intelligence(conn),
                "validation_outcomes": _validation_rollup(conn),
                "validation_outcome_intelligence": _validation_outcome_intelligence(conn),
                "research_decisions": _research_decision_rollup(conn),
                # research_blocker_resolution removed: blocker_resolution_records dropped mig 130
                # artifact_lineage_lifecycle removed: artifact_records dropped mig 130
                "dashboard_attention": _attention_rollup(conn),
                "route_status": _route_rollup(conn),
                "route_explainability": _route_explainability(conn),
                "drilldown_entry_points": _drilldown_entry_points(conn),
            },
        )


def project_telemetry_summary(project_id: str, db_path: Path | str | None = None) -> dict[str, Any]:
    with _connect(db_path) as conn:
        _require_tables(conn, (*CORE_TABLES, *FACT_TABLES))
        scope = ScopeFilter(project_id=project_id)
        return _scoped_summary(conn, "project_telemetry_summary", scope)


def milestone_telemetry_summary(
    milestone_id: str,
    *,
    project_id: str | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    with _connect(db_path) as conn:
        _require_tables(conn, (*CORE_TABLES, *FACT_TABLES))
        scope = ScopeFilter(project_id=project_id, milestone_id=milestone_id)
        return _scoped_summary(conn, "milestone_telemetry_summary", scope)


def task_telemetry_summary(
    task_id: str,
    *,
    project_id: str | None = None,
    milestone_id: str | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    with _connect(db_path) as conn:
        _require_tables(conn, (*CORE_TABLES, *FACT_TABLES))
        scope = ScopeFilter(project_id=project_id, milestone_id=milestone_id, task_id=task_id)
        return _scoped_summary(conn, "task_telemetry_summary", scope)


def process_run_timeline(process_run_id: str, db_path: Path | str | None = None) -> dict[str, Any]:
    """Return ordered events and associated telemetry facts for one process run."""

    with _connect(db_path) as conn:
        _require_tables(conn, (*CORE_TABLES, *FACT_TABLES))
        scope = ScopeFilter(process_run_id=process_run_id)
        source_tables = [
            "execution_events",
            # process_runs: dropped migration 131
            "token_usage_records",
            "validation_results",
            "findings_current_status",
            "research_evidence_records",
            # decision_records, outcome_records, dashboard_attention_items: dropped
            # migration 139 (WO-AI-SPINE, AD-5) — decisions/outcomes/attention below
            # are derived from execution_events (already listed above).
            # blocker_resolution_records: dropped migration 130
            # artifact_records: dropped migration 130
        ]
        return _with_authority(
            "process_run_timeline",
            source_tables,
            {
                "scope": _scope_dict(scope),
                "process_run": _first(
                    conn,
                    """
                    SELECT process_run_id,
                           min(project_id) AS project_id,
                           min(milestone_id) AS milestone_id,
                           min(task_id) AS task_id,
                           min(created_at) AS started_at,
                           max(created_at) AS ended_at
                    FROM execution_events
                    WHERE process_run_id = ?
                    GROUP BY process_run_id
                    """,
                    (process_run_id,),
                ),
                "events": _rows(
                    conn,
                    """
                    SELECT * FROM execution_events
                    WHERE process_run_id = ?
                    ORDER BY created_at, event_id
                    """,
                    (process_run_id,),
                ),
                "invocations": {
                    component: _rows(
                        conn,
                        f"SELECT * FROM execution_events "
                        f"WHERE process_run_id = ? AND {column} IS NOT NULL "
                        f"ORDER BY created_at, event_id",
                        (process_run_id,),
                    )
                    for component, (_table, column, _label) in COMPONENT_TABLES.items()
                },
                "tokens": (
                    _scoped_rows(
                        conn, "token_usage_records", scope, order_by="created_at, token_usage_id"
                    )
                    if _token_has_sqlite_table(conn)
                    else _token_rows_from_duckdb(scope)
                ),
                "validations": _scoped_rows(
                    conn, "validation_results", scope, order_by="created_at, validation_id"
                ),
                # findings retired in migration 112; findings_current_status lacks
                # process_run_id/milestone_id/task_id — use project-only rollup.
                "findings": _security_rollup(conn, scope),
                "research": _scoped_rows(
                    conn, "research_evidence_records", scope, order_by="created_at, research_id"
                ),
                "decisions": _scoped_rows_from_sql(
                    conn, _DECISION_EVENTS_VIEW_SQL, scope, order_by="created_at, decision_id"
                ),
                # blockers removed: blocker_resolution_records dropped migration 130
                # artifacts removed: artifact_records dropped migration 130
                "outcomes": _scoped_rows_from_sql(
                    conn, _OUTCOME_EVENTS_VIEW_SQL, scope, order_by="created_at, outcome_id"
                ),
                "attention": _scoped_rows_from_sql(
                    conn,
                    _ATTENTION_EVENTS_VIEW_SQL,
                    scope,
                    order_by="created_at, attention_id",
                ),
            },
        )


def workflow_execution_graph(workflow_id: str, db_path: Path | str | None = None) -> dict[str, Any]:
    """Return a derived workflow graph across process runs, events, validations, and outcomes."""

    with _connect(db_path) as conn:
        _require_tables(conn, (*CORE_TABLES, *FACT_TABLES))
        source_tables = [
            "execution_events",
            # process_runs: dropped migration 131
            "validation_results",
            # outcome_records: dropped migration 139 (WO-AI-SPINE, AD-5) — outcomes
            # below are derived from execution_events.
            "token_usage_records",
        ]
        invocations = _rows(
            conn,
            """
            SELECT * FROM execution_events
            WHERE workflow_id = ?
              AND event_type = 'workflow.invocation_recorded'
            ORDER BY created_at, event_id
            """,
            (workflow_id,),
        )
        process_run_ids = sorted(
            {row["process_run_id"] for row in invocations if row.get("process_run_id")}
        )
        event_ids = sorted({row["event_id"] for row in invocations if row.get("event_id")})
        nodes = [
            {
                "node_id": f"workflow:{workflow_id}",
                "node_type": "workflow",
                "label": workflow_id,
            }
        ]
        edges: list[dict[str, Any]] = []
        for process_run_id in process_run_ids:
            nodes.append(
                {
                    "node_id": f"process_run:{process_run_id}",
                    "node_type": "process_run",
                    "label": process_run_id,
                }
            )
            edges.append(
                {
                    "from": f"workflow:{workflow_id}",
                    "to": f"process_run:{process_run_id}",
                    "relationship": "observed_in_process_run",
                }
            )
        for event_id in event_ids:
            nodes.append(
                {
                    "node_id": f"event:{event_id}",
                    "node_type": "execution_event",
                    "label": event_id,
                }
            )
            edges.append(
                {
                    "from": f"workflow:{workflow_id}",
                    "to": f"event:{event_id}",
                    "relationship": "emitted_event",
                }
            )
        process_placeholders = ",".join("?" for _ in process_run_ids) or "NULL"
        process_params: tuple[Any, ...] = tuple(process_run_ids)
        return _with_authority(
            "workflow_execution_graph",
            source_tables,
            {
                "workflow_id": workflow_id,
                "nodes": nodes,
                "edges": edges,
                "invocations": invocations,
                # process_runs table dropped migration 131 — derive process-run rows
                # from execution_events.process_run_id (the live source).
                "process_runs": (
                    _rows(
                        conn,
                        f"SELECT process_run_id,"
                        f"  min(project_id) AS project_id,"
                        f"  min(milestone_id) AS milestone_id,"
                        f"  min(task_id) AS task_id,"
                        f"  min(created_at) AS started_at,"
                        f"  max(created_at) AS ended_at"
                        f" FROM execution_events"
                        f" WHERE process_run_id IN ({process_placeholders})"
                        f" GROUP BY process_run_id"
                        f" ORDER BY started_at, process_run_id",
                        process_params,
                    )
                    if process_run_ids
                    else []
                ),
                "events": (
                    _rows(
                        conn,
                        f"SELECT * FROM execution_events WHERE process_run_id IN ({process_placeholders}) ORDER BY created_at, event_id",
                        process_params,
                    )
                    if process_run_ids
                    else []
                ),
                "validations": (
                    _rows(
                        conn,
                        f"SELECT * FROM validation_results WHERE process_run_id IN ({process_placeholders}) ORDER BY created_at, validation_id",
                        process_params,
                    )
                    if process_run_ids
                    else []
                ),
                "outcomes": (
                    _rows(
                        conn,
                        f"SELECT * FROM ({_OUTCOME_EVENTS_VIEW_SQL}) AS outcome_view"
                        f" WHERE process_run_id IN ({process_placeholders})"
                        f" ORDER BY created_at, outcome_id",
                        process_params,
                    )
                    if process_run_ids
                    else []
                ),
                "tokens": (
                    _rows(
                        conn,
                        "SELECT * FROM token_usage_records WHERE workflow_id = ? ORDER BY created_at, token_usage_id",
                        (workflow_id,),
                    )
                    if _token_has_sqlite_table(conn)
                    else _token_rows_from_duckdb(workflow_id=workflow_id)
                ),
                "node_metadata_gap": {
                    "workflow_node_table_available": False,
                    "status": "deferred_until_workflow_node_runtime_metadata_exists",
                    "empty_state": "Workflow graph derives process/event/fact edges; node-level execution metadata is not persisted yet.",
                },
            },
        )


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
            rows = _component_usage(conn, table, column, component_id=component_id)
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


def dashboard_attention_summary(
    db_path: Path | str | None = None,
    *,
    status: str | None = None,
) -> dict[str, Any]:
    with _connect(db_path) as conn:
        # dashboard_attention_items: dropped migration 139 (WO-AI-SPINE, AD-5) —
        # attention items are now derived from execution_events.
        _require_tables(conn, ("execution_events",))
        where = "WHERE status = ?" if status else ""
        params: tuple[Any, ...] = (status,) if status else ()
        items = _rows(
            conn,
            f"""
            SELECT * FROM ({_ATTENTION_EVENTS_VIEW_SQL})
            {where}
            ORDER BY prompt_required DESC, operator_action_required DESC, action_required DESC,
                     severity DESC, created_at ASC, attention_id ASC
            """,
            params,
        )
        return _with_authority(
            "dashboard_attention_summary",
            ["execution_events"],
            {
                "status_filter": status,
                "open_items": [item for item in items if item.get("status") == "open"],
                "grouped_items": _attention_groups(conn, status=status),
                "prompt_required_items": [
                    item for item in items if item.get("prompt_required") == 1
                ],
                "approval_required_items": [
                    item for item in items if item.get("operator_action_required") == 1
                ],
                "warning_items": [item for item in items if item.get("severity") == "warning"],
                "informational_items": [item for item in items if item.get("severity") == "info"],
                "rollup": _attention_rollup(conn),
            },
        )


def _scoped_summary(
    conn: sqlite3.Connection, model_name: str, scope: ScopeFilter
) -> dict[str, Any]:
    source_tables = list(dict.fromkeys((*CORE_TABLES, *FACT_TABLES)))
    return _with_authority(
        model_name,
        source_tables,
        {
            "scope": _scope_dict(scope),
            "entity_counts": _entity_counts(conn, scope),
            "process_runs": _process_runs_from_events(conn, scope),
            "events": _scoped_rows(
                conn, "execution_events", scope, order_by="created_at DESC, event_id"
            ),
            "component_usage": {
                component: _component_usage(conn, table, column, scope=scope)
                for component, (table, column, _label) in COMPONENT_TABLES.items()
            },
            "tokens": _token_rollup(conn, scope=scope),
            "token_cost_intelligence": _token_cost_intelligence(conn, scope),
            "ai_usage_accounting": adapter_usage_accounting_summary(
                conn, project_id=scope.project_id
            ),
            "findings": _security_rollup(conn, scope),
            "security_remediation_intelligence": _security_remediation_intelligence(conn, scope),
            "validations": _validation_rollup(conn, scope),
            "validation_outcome_intelligence": _validation_outcome_intelligence(conn, scope),
            "research_decisions": _research_decision_rollup(conn, scope),
            # research_blocker_resolution removed: blocker_resolution_records dropped mig 130
            # artifact_lineage_lifecycle removed: artifact_records dropped mig 130
            "attention": _attention_rollup(conn, scope),
            "outcomes": _outcome_rollup(conn, scope),
            "route_status": _route_rollup(conn, scope),
        },
    )


def _connect(db_path: Path | str | None) -> sqlite3.Connection:
    path = Path(db_path) if db_path is not None else get_db_path()
    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def _require_tables(conn: sqlite3.Connection, tables: Sequence[str]) -> None:
    missing = [
        table
        for table in tables
        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        is None
    ]
    if missing:
        raise RuntimeError(f"telemetry read model tables missing: {', '.join(missing)}")


def _with_authority(
    model_name: str, source_tables: Sequence[str], payload: Mapping[str, Any]
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return {
        "model_name": model_name,
        "derived_view": True,
        "primary_authority": False,
        "source_tables": list(dict.fromkeys(source_tables)),
        "generated_at": generated_at,
        "freshness": {
            "generated_at": generated_at,
            "stale": False,
            "staleness_basis": "query_time_snapshot",
        },
        "empty_state_behavior": "Return zero counts and empty lists when telemetry facts are absent.",
        **dict(payload),
    }


def _entity_counts(conn: sqlite3.Connection, scope: ScopeFilter | None = None) -> dict[str, int]:
    return {
        "projects": _distinct_count(conn, "execution_events", "project_id", scope),
        "milestones": _distinct_count(conn, "execution_events", "milestone_id", scope),
        "tasks": _distinct_count(conn, "execution_events", "task_id", scope),
        "process_runs": _distinct_count(conn, "execution_events", "process_run_id", scope),
        "events": _row_count(conn, "execution_events", scope),
    }


def _table_counts(conn: sqlite3.Connection, tables: Iterable[str]) -> dict[str, int]:
    return {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}


def _distinct_count(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    scope: ScopeFilter | None = None,
) -> int:
    where, params = _where_scope(scope)
    return int(
        conn.execute(
            (
                f"SELECT COUNT(DISTINCT {column}) FROM {table} {where} AND {column} IS NOT NULL"
                if where
                else f"SELECT COUNT(DISTINCT {column}) FROM {table} WHERE {column} IS NOT NULL"
            ),
            params,
        ).fetchone()[0]
        or 0
    )


def _row_count(conn: sqlite3.Connection, table: str, scope: ScopeFilter | None = None) -> int:
    where, params = _where_scope(scope)
    return int(conn.execute(f"SELECT COUNT(*) FROM {table} {where}", params).fetchone()[0] or 0)


def _outcome_row_count(conn: sqlite3.Connection, scope: ScopeFilter | None = None) -> int:
    """Like _row_count, but over the execution_events-derived outcome view
    (outcome_records dropped migration 139, WO-AI-SPINE)."""
    where, params = _where_scope(scope)
    return int(
        conn.execute(
            f"SELECT COUNT(*) FROM ({_OUTCOME_EVENTS_VIEW_SQL}) {where}", params
        ).fetchone()[0]
        or 0
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
        for row in _component_usage(conn, table, column)[:3]:
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
        for usage in _component_usage(conn, table, column)[:10]:
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
                    # findings_current_status lacks milestone_id/task_id/process_run_id
                    "security_finding_count": _row_count(
                        conn,
                        "findings_current_status",
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


_REPORTABLE_COST_VISIBILITIES = frozenset(
    {"exact", "provider_reported", "estimated", "allocated_subscription_cost"}
)

_TOKEN_ROLLUP_DIM_DEFAULTS: tuple[tuple[str, str], ...] = (
    ("project_id", "unknown"),
    ("milestone_id", "unknown"),
    ("task_id", "unknown"),
    ("process_run_id", "unknown"),
    ("agent_id", "unknown"),
    ("skill_id", "unknown"),
    ("workflow_id", "unknown"),
    ("hook_id", "unknown"),
    ("adapter_id", "unknown"),
    ("model_id", "unknown"),
    ("provider", "unknown"),
    ("billing_mode", "unknown"),
    ("token_visibility", "unavailable"),
    ("cost_visibility", "unknown"),
    ("usage_source", "unavailable"),
    ("cost_source", "unknown"),
    ("accounting_confidence", "unknown"),
)


def _token_has_sqlite_table(conn: sqlite3.Connection) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'token_usage_records'"
        ).fetchone()
        is not None
    )


def _token_rows_from_duckdb(
    scope: ScopeFilter | None = None, *, workflow_id: str | None = None
) -> list[dict[str, Any]]:
    """Raw (ungrouped) DuckDB token rows, filtered and ordered like the retired
    ``SELECT * FROM token_usage_records WHERE ... ORDER BY created_at,
    token_usage_id`` queries (process_run_timeline, workflow_execution_graph)."""
    from projections.core.collectors.authority_sources import fetch_token_usage_records

    rows = fetch_token_usage_records() or []
    out: list[dict[str, Any]] = []
    for row in rows:
        if scope is not None:
            if scope.project_id is not None and row.get("project_id") != scope.project_id:
                continue
            if scope.milestone_id is not None and row.get("milestone_id") != scope.milestone_id:
                continue
            if scope.task_id is not None and row.get("task_id") != scope.task_id:
                continue
            # process_run_id not filtered — see _duckdb_token_rollup.
        if workflow_id is not None and row.get("workflow_id") != workflow_id:
            continue
        out.append(row)
    out.sort(key=lambda r: (r.get("created_at") or "", r.get("token_usage_id") or ""))
    return out


def _duckdb_token_rollup(
    scope: ScopeFilter | None,
    *,
    component_type: str | None = None,
    component_id: str | None = None,
    include_purpose: bool = False,
) -> list[dict[str, Any]]:
    """Group DuckDB token_usage_records view rows the same way the retired
    SQLite GROUP BY query did (WO-DBA-DROP, migration 137)."""
    from projections.core.collectors.authority_sources import fetch_token_usage_records

    rows = fetch_token_usage_records() or []
    component_column = (
        {
            "agent": "agent_id",
            "skill": "skill_id",
            "workflow": "workflow_id",
            "hook": "hook_id",
            "model": "model_id",
        }.get(component_type)
        if component_type
        else None
    )

    groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        if scope is not None:
            if scope.project_id is not None and row.get("project_id") != scope.project_id:
                continue
            if scope.milestone_id is not None and row.get("milestone_id") != scope.milestone_id:
                continue
            if scope.task_id is not None and row.get("task_id") != scope.task_id:
                continue
            # process_run_id is deliberately NOT filtered: canonical
            # token.consumed events carry no process_run_id (the DuckDB view
            # hard-codes NULL for it — see core/analytics/duckdb_store.py), so
            # requiring an exact match would always exclude every row. Filter
            # to the finest-grained dimension that is actually populated.
        if (
            component_column
            and component_id is not None
            and row.get(component_column) != component_id
        ):
            continue

        dims = {name: (row.get(name) or default) for name, default in _TOKEN_ROLLUP_DIM_DEFAULTS}
        if include_purpose:
            dims["purpose"] = row.get("purpose") or "unknown"
        key = tuple(dims.values())
        bucket = groups.setdefault(
            key,
            {
                **dims,
                "input_tokens": 0,
                "output_tokens": 0,
                "cached_tokens": 0,
                "total_tokens": 0,
                "record_count": 0,
                "reportable_cost": None,
            },
        )
        bucket["input_tokens"] += int(row.get("input_tokens") or 0)
        bucket["output_tokens"] += int(row.get("output_tokens") or 0)
        bucket["cached_tokens"] += int(row.get("cached_tokens") or 0)
        bucket["total_tokens"] += int(row.get("total_tokens") or 0)
        bucket["record_count"] += 1
        if dims["cost_visibility"] in _REPORTABLE_COST_VISIBILITIES:
            cost = float(row.get("estimated_cost") or 0)
            bucket["reportable_cost"] = (bucket["reportable_cost"] or 0.0) + cost

    out = list(groups.values())
    if include_purpose:
        for bucket in out:
            total = bucket["total_tokens"]
            reportable = bucket["reportable_cost"]
            bucket["reportable_cost_per_1k_tokens"] = (
                round((reportable / total) * 1000, 6)
                if reportable is not None and total > 0
                else None
            )
        out.sort(
            key=lambda b: (b["reportable_cost"] or 0, b["total_tokens"], b["record_count"]),
            reverse=True,
        )
    else:
        out.sort(key=lambda b: (b["total_tokens"], b["record_count"]), reverse=True)
    return out


def _token_rollup(
    conn: sqlite3.Connection,
    *,
    scope: ScopeFilter | None = None,
    component_type: str | None = None,
    component_id: str | None = None,
) -> list[dict[str, Any]]:
    if not _token_has_sqlite_table(conn):
        # WO-DBA-DROP (migration 137): token_usage_records is no longer a
        # SQLite table in a fresh install — read the DuckDB view instead.
        return _duckdb_token_rollup(scope, component_type=component_type, component_id=component_id)

    where, params = _where_scope(scope)
    if component_type and component_id:
        column = {
            "agent": "agent_id",
            "skill": "skill_id",
            "workflow": "workflow_id",
            "hook": "hook_id",
            "model": "model_id",
        }.get(component_type)
        if column:
            where, params = _add_condition(where, params, f"{column} = ?", component_id)
    return _rows(
        conn,
        f"""
        SELECT
            COALESCE(project_id, 'unknown') AS project_id,
            COALESCE(milestone_id, 'unknown') AS milestone_id,
            COALESCE(task_id, 'unknown') AS task_id,
            COALESCE(process_run_id, 'unknown') AS process_run_id,
            COALESCE(agent_id, 'unknown') AS agent_id,
            COALESCE(skill_id, 'unknown') AS skill_id,
            COALESCE(workflow_id, 'unknown') AS workflow_id,
            COALESCE(hook_id, 'unknown') AS hook_id,
            COALESCE(adapter_id, 'unknown') AS adapter_id,
            COALESCE(model_id, 'unknown') AS model_id,
            COALESCE(provider, 'unknown') AS provider,
            COALESCE(billing_mode, 'unknown') AS billing_mode,
            COALESCE(token_visibility, 'unavailable') AS token_visibility,
            COALESCE(cost_visibility, 'unknown') AS cost_visibility,
            COALESCE(usage_source, 'unavailable') AS usage_source,
            COALESCE(cost_source, 'unknown') AS cost_source,
            COALESCE(accounting_confidence, 'unknown') AS accounting_confidence,
            SUM(input_tokens) AS input_tokens,
            SUM(output_tokens) AS output_tokens,
            SUM(cached_tokens) AS cached_tokens,
            SUM(total_tokens) AS total_tokens,
            CASE
                WHEN COALESCE(cost_visibility, 'unknown') IN (
                    'exact',
                    'provider_reported',
                    'estimated',
                    'allocated_subscription_cost'
                ) THEN SUM(estimated_cost)
                ELSE NULL
            END AS reportable_cost,
            COUNT(*) AS record_count
        FROM token_usage_records
        {where}
        GROUP BY project_id, milestone_id, task_id, process_run_id,
                 agent_id, skill_id, workflow_id, hook_id, adapter_id, model_id,
                 provider, billing_mode, token_visibility, cost_visibility,
                 usage_source, cost_source, accounting_confidence
        ORDER BY total_tokens DESC, record_count DESC
        """,
        params,
    )


def _token_cost_intelligence(
    conn: sqlite3.Connection, scope: ScopeFilter | None = None
) -> dict[str, Any]:
    if not _token_has_sqlite_table(conn):
        # WO-DBA-DROP (migration 137): token_usage_records is no longer a
        # SQLite table in a fresh install — read the DuckDB view instead.
        by_model_provider = _duckdb_token_rollup(scope, include_purpose=True)
    else:
        where, params = _where_scope(scope)
        by_model_provider = _rows(
            conn,
            f"""
            SELECT
                COALESCE(project_id, 'unknown') AS project_id,
                COALESCE(milestone_id, 'unknown') AS milestone_id,
                COALESCE(task_id, 'unknown') AS task_id,
                COALESCE(process_run_id, 'unknown') AS process_run_id,
                COALESCE(agent_id, 'unknown') AS agent_id,
                COALESCE(skill_id, 'unknown') AS skill_id,
                COALESCE(workflow_id, 'unknown') AS workflow_id,
                COALESCE(hook_id, 'unknown') AS hook_id,
                COALESCE(adapter_id, 'unknown') AS adapter_id,
                COALESCE(model_id, 'unknown') AS model_id,
                COALESCE(provider, 'unknown') AS provider,
                COALESCE(purpose, 'unknown') AS purpose,
                COALESCE(billing_mode, 'unknown') AS billing_mode,
                COALESCE(token_visibility, 'unavailable') AS token_visibility,
                COALESCE(cost_visibility, 'unknown') AS cost_visibility,
                COALESCE(usage_source, 'unavailable') AS usage_source,
                COALESCE(cost_source, 'unknown') AS cost_source,
                COALESCE(accounting_confidence, 'unknown') AS accounting_confidence,
                SUM(input_tokens) AS input_tokens,
                SUM(output_tokens) AS output_tokens,
                SUM(cached_tokens) AS cached_tokens,
                SUM(total_tokens) AS total_tokens,
                CASE
                    WHEN COALESCE(cost_visibility, 'unknown') IN (
                        'exact',
                        'provider_reported',
                        'estimated',
                        'allocated_subscription_cost'
                    ) THEN SUM(estimated_cost)
                    ELSE NULL
                END AS reportable_cost,
                COUNT(*) AS record_count,
                CASE
                    WHEN COALESCE(cost_visibility, 'unknown') IN (
                        'exact',
                        'provider_reported',
                        'estimated',
                        'allocated_subscription_cost'
                    ) AND SUM(total_tokens) > 0
                    THEN ROUND((SUM(estimated_cost) / SUM(total_tokens)) * 1000, 6)
                    ELSE NULL
                END AS reportable_cost_per_1k_tokens
            FROM token_usage_records
            {where}
            GROUP BY project_id, milestone_id, task_id, process_run_id,
                     agent_id, skill_id, workflow_id, hook_id, adapter_id, model_id,
                     provider, purpose, billing_mode, token_visibility, cost_visibility,
                     usage_source, cost_source, accounting_confidence
            ORDER BY COALESCE(reportable_cost, 0) DESC, total_tokens DESC, record_count DESC
            """,
            params,
        )
    outcome_correlations: list[dict[str, Any]] = []
    for row in by_model_provider:
        row_scope = _scope_from_rollup_row(row)
        outcomes = _outcome_rollup(conn, row_scope)
        outcome_correlations.append(
            {
                "project_id": row["project_id"],
                "milestone_id": row["milestone_id"],
                "task_id": row["task_id"],
                "process_run_id": row["process_run_id"],
                "agent_id": row["agent_id"],
                "skill_id": row["skill_id"],
                "workflow_id": row["workflow_id"],
                "hook_id": row["hook_id"],
                "adapter_id": row["adapter_id"],
                "model_id": row["model_id"],
                "provider": row["provider"],
                "total_tokens": row["total_tokens"],
                "reportable_cost": row["reportable_cost"],
                "cost_display": (
                    row["reportable_cost"] if row["reportable_cost"] is not None else "unknown"
                ),
                "billing_mode": row["billing_mode"],
                "token_visibility": row["token_visibility"],
                "cost_visibility": row["cost_visibility"],
                "usage_source": row["usage_source"],
                "cost_source": row["cost_source"],
                "confidence": row["accounting_confidence"],
                "outcomes": outcomes,
                "has_outcome_signal": bool(outcomes),
                "dashboard_ready": True,
                "derived_view": True,
                "primary_authority": False,
            }
        )
    return {
        "by_model_provider_component": by_model_provider,
        "outcome_correlations": outcome_correlations,
        "highest_reportable_cost": [
            row for row in by_model_provider if row["reportable_cost"] is not None
        ][:10],
        "retry_patterns": {
            "available": False,
            "reason": "token_usage_records does not persist retry attempt metadata yet",
            "future_source_candidates": [
                "workflow node retry metadata",
                "route decision retry metadata",
            ],
        },
        "policy": {
            "derived_view": True,
            "primary_authority": False,
            "provider_billing_authority": False,
            "tokens_are_usage_not_cost": True,
            "do_not_convert_plan_tokens_to_dollars": True,
            "execution_authorized": False,
        },
        "empty_state": "No token usage records for the selected scope.",
    }


def _security_rollup(
    conn: sqlite3.Connection, scope: ScopeFilter | None = None
) -> list[dict[str, Any]]:
    # findings retired in migration 112 (WO-Y); read from findings_current_status spine.
    where, params = _where_scope_project_only(scope)
    try:
        return _rows(
            conn,
            f"""
            SELECT
                COALESCE(project_id, 'unknown') AS project_id,
                COALESCE(file_path, 'unknown') AS file_path,
                line_number AS start_line,
                NULL AS end_line,
                severity,
                current_status AS status,
                COUNT(*) AS finding_count
            FROM findings_current_status
            {where}
            GROUP BY project_id, file_path, line_number, severity, current_status
            ORDER BY finding_count DESC, severity DESC, file_path
            """,
            params,
        )
    except Exception:
        return []


def _security_remediation_intelligence(
    conn: sqlite3.Connection,
    scope: ScopeFilter | None = None,
) -> dict[str, Any]:
    # findings retired in migration 112 (WO-Y); read from findings_current_status spine.
    # Use fcs.project_id to avoid "ambiguous column name" in the LEFT JOIN.
    if scope and scope.project_id:
        fcs_where = "WHERE fcs.project_id = ?"
        params: tuple[Any, ...] = (scope.project_id,)
    else:
        fcs_where = ""
        params = ()
    try:
        findings = _rows(
            conn,
            f"""
            SELECT
                fcs.finding_id,
                COALESCE(fcs.project_id, 'unknown') AS project_id,
                'unknown' AS milestone_id,
                'unknown' AS task_id,
                'unknown' AS process_run_id,
                'unknown' AS scan_id,
                fcs.severity,
                COALESCE(se.vuln_class, 'unknown') AS category,
                COALESCE(se.vuln_class, 'unknown') AS rule_id,
                COALESCE(fcs.file_path, 'unknown') AS file_path,
                fcs.line_number AS start_line,
                NULL AS end_line,
                fcs.current_status AS status,
                NULL AS recommendation,
                'unknown' AS agent_id,
                'unknown' AS skill_id,
                'unknown' AS workflow_id,
                'unknown' AS hook_id,
                NULL AS evidence_refs_json,
                fcs.created_at,
                fcs.updated_at
            FROM findings_current_status fcs
            LEFT JOIN security_events se ON se.event_id = fcs.finding_id
            {fcs_where}
            ORDER BY
                CASE fcs.severity
                WHEN 'critical' THEN 0
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
                ELSE 4
            END,
            status,
            file_path,
            start_line
            """,
            params,
        )
    except Exception:
        findings = []
    remediation_candidates = [
        {
            **finding,
            "candidate_type": "security_remediation_work_order_candidate",
            "requires_future_approval": True,
            "execution_authorized": False,
            "remediation_basis": "open_security_finding",
        }
        for finding in findings
        if finding["status"] in {"open", "unresolved"}
        and finding["severity"] in {"critical", "high", "medium"}
    ]
    false_positive_candidates = [
        finding
        for finding in findings
        if finding["status"] in {"false_positive", "false-positive", "dismissed"}
    ]
    resolved_findings = [
        finding for finding in findings if finding["status"] in {"resolved", "fixed", "closed"}
    ]

    return {
        "findings": findings,
        "status_counts": _security_status_counts(conn, scope),
        "attribution": _security_attribution(conn, scope),
        "remediation_candidates": remediation_candidates,
        "false_positive_candidates": false_positive_candidates,
        "resolved_findings": resolved_findings,
        "remediation_policy": {
            "execution_authorized": False,
            "requires_future_work_order": True,
            "requires_human_approval": True,
            "db_record_deletion_allowed": False,
            "dashboard_ready": True,
            "derived_view": True,
            "primary_authority": False,
        },
        "empty_state": "No security findings for the selected scope.",
    }


def _security_status_counts(
    conn: sqlite3.Connection, scope: ScopeFilter | None = None
) -> list[dict[str, Any]]:
    # findings retired in migration 112 (WO-Y); read from findings_current_status spine.
    where, params = _where_scope_project_only(scope)
    try:
        return _rows(
            conn,
            f"""
            SELECT
                COALESCE(project_id, 'unknown') AS project_id,
                severity,
                current_status AS status,
                COUNT(*) AS finding_count
            FROM findings_current_status
            {where}
            GROUP BY project_id, severity, current_status
            ORDER BY finding_count DESC, severity, current_status
            """,
            params,
        )
    except Exception:
        return []


def _security_attribution(
    conn: sqlite3.Connection, scope: ScopeFilter | None = None
) -> list[dict[str, Any]]:
    # findings retired in migration 112 (WO-Y); attribution columns not on spine.
    # Return project/severity/status summary only; agent attribution is empty.
    where, params = _where_scope_project_only(scope)
    try:
        return _rows(
            conn,
            f"""
            SELECT
                COALESCE(project_id, 'unknown') AS project_id,
                'unknown' AS agent_id,
                'unknown' AS skill_id,
                'unknown' AS workflow_id,
                'unknown' AS hook_id,
                severity,
                current_status AS status,
                COUNT(*) AS finding_count
            FROM findings_current_status
            {where}
            GROUP BY project_id, severity, current_status
            ORDER BY finding_count DESC, severity DESC
            """,
            params,
        )
    except Exception:
        return []


def _validation_rollup(
    conn: sqlite3.Connection, scope: ScopeFilter | None = None
) -> list[dict[str, Any]]:
    where, params = _where_scope(scope)
    return _rows(
        conn,
        f"""
        SELECT
            COALESCE(project_id, 'unknown') AS project_id,
            COALESCE(milestone_id, 'unknown') AS milestone_id,
            COALESCE(task_id, 'unknown') AS task_id,
            COALESCE(process_run_id, 'unknown') AS process_run_id,
            validation_type AS component_id,
            status,
            COUNT(*) AS validation_count
        FROM validation_results
        {where}
        GROUP BY project_id, milestone_id, task_id, process_run_id, validation_type, status
        ORDER BY validation_count DESC, validation_type
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
                # findings_current_status lacks milestone_id/task_id/process_run_id
                "security_finding_count": _row_count(
                    conn,
                    "findings_current_status",
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


def _research_decision_rollup(
    conn: sqlite3.Connection, scope: ScopeFilter | None = None
) -> dict[str, Any]:
    where, params = _where_scope(scope)
    research = _rows(
        conn,
        f"""
        SELECT
            COALESCE(project_id, 'unknown') AS project_id,
            COALESCE(milestone_id, 'unknown') AS milestone_id,
            COALESCE(task_id, 'unknown') AS task_id,
            decision_class,
            confidence,
            operator_verification_required,
            COUNT(*) AS research_count
        FROM research_evidence_records
        {where}
        GROUP BY project_id, milestone_id, task_id, decision_class, confidence, operator_verification_required
        ORDER BY research_count DESC, decision_class
        """,
        params,
    )
    decisions = _rows(
        conn,
        f"""
        SELECT
            COALESCE(project_id, 'unknown') AS project_id,
            COALESCE(milestone_id, 'unknown') AS milestone_id,
            COALESCE(task_id, 'unknown') AS task_id,
            decision_type,
            decision_status,
            selected_option,
            COUNT(*) AS decision_count
        FROM ({_DECISION_EVENTS_VIEW_SQL})
        {where}
        GROUP BY project_id, milestone_id, task_id, decision_type, decision_status, selected_option
        ORDER BY decision_count DESC, decision_type
        """,
        params,
    )
    return {"research": research, "decisions": decisions}


def _attention_rollup(
    conn: sqlite3.Connection, scope: ScopeFilter | None = None
) -> list[dict[str, Any]]:
    where, params = _where_scope(scope)
    return _rows(
        conn,
        f"""
        SELECT
            COALESCE(project_id, 'unknown') AS project_id,
            COALESCE(milestone_id, 'unknown') AS milestone_id,
            COALESCE(task_id, 'unknown') AS task_id,
            COALESCE(process_run_id, 'unknown') AS process_run_id,
            attention_type,
            severity,
            status,
            action_required,
            operator_action_required,
            prompt_required,
            COUNT(*) AS item_count
        FROM ({_ATTENTION_EVENTS_VIEW_SQL})
        {where}
        GROUP BY project_id, milestone_id, task_id, process_run_id,
                 attention_type, severity, status,
                 action_required, operator_action_required, prompt_required
        ORDER BY prompt_required DESC, operator_action_required DESC, item_count DESC
        """,
        params,
    )


def _attention_groups(
    conn: sqlite3.Connection, *, status: str | None = None
) -> list[dict[str, Any]]:
    where = "WHERE status = ?" if status else ""
    params: tuple[Any, ...] = (status,) if status else ()
    return _rows(
        conn,
        f"""
        SELECT
            attention_type,
            severity,
            status,
            action_required,
            operator_action_required,
            prompt_required,
            COUNT(*) AS item_count,
            MAX(created_at) AS latest_created_at,
            MIN(title) AS example_title
        FROM ({_ATTENTION_EVENTS_VIEW_SQL})
        {where}
        GROUP BY attention_type, severity, status,
                 action_required, operator_action_required, prompt_required
        ORDER BY prompt_required DESC, operator_action_required DESC,
                 action_required DESC, item_count DESC, latest_created_at DESC
        """,
        params,
    )


def _outcome_rollup(
    conn: sqlite3.Connection, scope: ScopeFilter | None = None
) -> list[dict[str, Any]]:
    where, params = _where_scope(scope)
    return _rows(
        conn,
        f"""
        SELECT
            COALESCE(project_id, 'unknown') AS project_id,
            COALESCE(milestone_id, 'unknown') AS milestone_id,
            COALESCE(task_id, 'unknown') AS task_id,
            outcome_type,
            outcome_status,
            COUNT(*) AS outcome_count
        FROM ({_OUTCOME_EVENTS_VIEW_SQL})
        {where}
        GROUP BY project_id, milestone_id, task_id, outcome_type, outcome_status
        ORDER BY outcome_count DESC, outcome_type
        """,
        params,
    )


def _route_rollup(
    conn: sqlite3.Connection, scope: ScopeFilter | None = None
) -> list[dict[str, Any]]:
    # route_decision_records dropped migration 131 — return empty gracefully
    return []


def _route_explainability(
    conn: sqlite3.Connection, scope: ScopeFilter | None = None
) -> list[dict[str, Any]]:
    # route_decision_records dropped migration 131 — return empty gracefully
    return []


def _scoped_rows(
    conn: sqlite3.Connection,
    table: str,
    scope: ScopeFilter,
    *,
    order_by: str,
) -> list[dict[str, Any]]:
    where, params = _where_scope(scope)
    return _rows(conn, f"SELECT * FROM {table} {where} ORDER BY {order_by}", params)


def _scoped_rows_from_sql(
    conn: sqlite3.Connection,
    view_sql: str,
    scope: ScopeFilter,
    *,
    order_by: str,
) -> list[dict[str, Any]]:
    """Like _scoped_rows, but over a derived-view SQL fragment (e.g. the
    execution_events projections for decisions/outcomes/attention — see
    _DECISION_EVENTS_VIEW_SQL / _OUTCOME_EVENTS_VIEW_SQL / _ATTENTION_EVENTS_VIEW_SQL)
    instead of a real table name."""
    where, params = _where_scope(scope)
    return _rows(conn, f"SELECT * FROM ({view_sql}) {where} ORDER BY {order_by}", params)


def _process_runs_from_events(
    conn: sqlite3.Connection, scope: ScopeFilter | None
) -> list[dict[str, Any]]:
    """Derive process-run summaries from execution_events.process_run_id.

    process_runs is an empty table because no process.* events are emitted by
    the current runtime. This helper builds equivalent summaries from the
    execution_events rows that carry process_run_id, which have real data.
    """
    where, params = _where_scope(scope)
    extra = f" AND {where[6:]}" if where else ""
    return _rows(
        conn,
        f"SELECT process_run_id,"
        f"  min(project_id) AS project_id,"
        f"  min(milestone_id) AS milestone_id,"
        f"  min(task_id) AS task_id,"
        f"  min(created_at) AS started_at,"
        f"  max(created_at) AS ended_at"
        f" FROM execution_events"
        f" WHERE process_run_id IS NOT NULL{extra}"
        f" GROUP BY process_run_id"
        f" ORDER BY started_at DESC",
        params,
    )


def _where_scope(scope: ScopeFilter | None) -> tuple[str, tuple[Any, ...]]:
    if scope is None:
        return "", ()
    clauses: list[str] = []
    params: list[Any] = []
    for column, value in (
        ("project_id", scope.project_id),
        ("milestone_id", scope.milestone_id),
        ("task_id", scope.task_id),
        ("process_run_id", scope.process_run_id),
    ):
        if value is not None:
            clauses.append(f"{column} = ?")
            params.append(value)
    if not clauses:
        return "", ()
    return "WHERE " + " AND ".join(clauses), tuple(params)


def _where_scope_project_only(scope: ScopeFilter | None) -> tuple[str, tuple[Any, ...]]:
    """Like _where_scope but only filters project_id — safe for spine tables
    that lack milestone_id / task_id / process_run_id columns."""
    if scope is None or scope.project_id is None:
        return "", ()
    return "WHERE project_id = ?", (scope.project_id,)


def _add_condition(
    where: str,
    params: tuple[Any, ...],
    condition: str,
    value: Any,
) -> tuple[str, tuple[Any, ...]]:
    prefix = "WHERE" if not where else f"{where} AND"
    return f"{prefix} {condition}", (*params, value)


def _scope_dict(scope: ScopeFilter) -> dict[str, str | None]:
    return {
        "project_id": scope.project_id,
        "milestone_id": scope.milestone_id,
        "task_id": scope.task_id,
        "process_run_id": scope.process_run_id,
    }


def _scope_from_rollup_row(row: Mapping[str, Any]) -> ScopeFilter:
    return ScopeFilter(
        project_id=_none_if_unknown(row.get("project_id")),
        milestone_id=_none_if_unknown(row.get("milestone_id")),
        task_id=_none_if_unknown(row.get("task_id")),
        process_run_id=_none_if_unknown(row.get("process_run_id")),
    )


def _none_if_unknown(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return None if not text or text == "unknown" else text


def _source_tables_for_components(components: Mapping[str, tuple[str, str, str]]) -> list[str]:
    tables = [
        "execution_events",
        "token_usage_records",
        "validation_results",
        "findings_current_status",  # findings retired in migration 112
        # outcome_records: dropped migration 139 (WO-AI-SPINE, AD-5) — outcomes are
        # derived from execution_events, already listed above.
    ]
    tables.extend(table for table, _column, _label in components.values())
    return list(dict.fromkeys(tables))


def _rows(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]


def _first(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
    row = conn.execute(sql, tuple(params)).fetchone()
    return dict(row) if row is not None else None


def _json_list(value: Any) -> list[Any]:
    if not value:
        return []
    try:
        import json

        parsed = json.loads(str(value))
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _json_object(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    try:
        import json

        parsed = json.loads(str(value))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
