"""WO-GF-TELEMETRY-SPLIT: read_models attention/outcome/decision rollups.

Extracted verbatim from core/telemetry/read_models.py (see read_models.py
facade). dashboard_attention_summary (PUBLIC), _research_decision_rollup,
_attention_rollup, _attention_groups, _outcome_rollup, _route_rollup (dead),
_route_explainability (dead).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .read_models_shared import (
    ScopeFilter,
    _ATTENTION_EVENTS_VIEW_SQL,
    _DECISION_EVENTS_VIEW_SQL,
    _OUTCOME_EVENTS_VIEW_SQL,
    _connect,
    _require_tables,
    _rows,
    _where_scope,
    _with_authority,
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
