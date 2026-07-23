"""WO-GF-TELEMETRY-SPLIT: read_models process-run timeline and workflow graph.

Extracted verbatim from core/telemetry/read_models.py (see read_models.py
facade). process_run_timeline (PUBLIC), workflow_execution_graph (PUBLIC,
pre-existing but unwired to any dashboard route — preserved anyway).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .read_models_security import _security_rollup
from .read_models_shared import (
    COMPONENT_TABLES,
    CORE_TABLES,
    FACT_TABLES,
    ScopeFilter,
    _ATTENTION_EVENTS_VIEW_SQL,
    _DECISION_EVENTS_VIEW_SQL,
    _OUTCOME_EVENTS_VIEW_SQL,
    _connect,
    _first,
    _require_tables,
    _rows,
    _scope_dict,
    _scoped_rows,
    _scoped_rows_from_sql,
    _with_authority,
)
from .read_models_tokens import _token_has_sqlite_table, _token_rows_from_duckdb


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
            # findings_current_status: dropped migration 140 (WO dff23cb0) —
            # derived from security_events at read time (see below "findings").
            "security_events",
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
