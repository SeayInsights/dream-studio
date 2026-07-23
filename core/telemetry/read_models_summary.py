"""WO-GF-TELEMETRY-SPLIT: read_models global/project/milestone/task summaries.

Extracted verbatim from core/telemetry/read_models.py (see read_models.py
facade). global_telemetry_summary, project_telemetry_summary,
milestone_telemetry_summary, task_telemetry_summary (all PUBLIC),
_scoped_summary.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from core.shared_intelligence.usage_accounting import adapter_usage_accounting_summary

from .read_models_components import _component_usage_rows, _drilldown_entry_points
from .read_models_outcomes import (
    _attention_rollup,
    _outcome_rollup,
    _research_decision_rollup,
    _route_explainability,
    _route_rollup,
)
from .read_models_security import _security_remediation_intelligence, _security_rollup
from .read_models_shared import (
    COMPONENT_TABLES,
    CORE_TABLES,
    FACT_TABLES,
    ScopeFilter,
    _connect,
    _entity_counts,
    _process_runs_from_events,
    _require_tables,
    _scope_dict,
    _scoped_rows,
    _table_counts,
    _with_authority,
)
from .read_models_tokens import _token_cost_intelligence, _token_rollup
from .read_models_validation import _validation_outcome_intelligence, _validation_rollup


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
                    component: _component_usage_rows(conn, component, table, column)
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
                component: _component_usage_rows(conn, component, table, column, scope=scope)
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
