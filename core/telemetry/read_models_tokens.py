"""WO-GF-TELEMETRY-SPLIT: read_models token usage and cost intelligence.

Extracted verbatim from core/telemetry/read_models.py (see read_models.py
facade). _REPORTABLE_COST_VISIBILITIES, _TOKEN_ROLLUP_DIM_DEFAULTS,
_token_has_sqlite_table, _token_rows_from_duckdb, _duckdb_token_rollup,
_token_rollup, _token_cost_intelligence.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from .read_models_outcomes import _outcome_rollup
from .read_models_shared import (
    ScopeFilter,
    _add_condition,
    _rows,
    _scope_from_rollup_row,
    _where_scope,
)

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
