"""WO-GF-TELEMETRY-SPLIT: read_models shared primitives.

Extracted verbatim from core/telemetry/read_models.py (see read_models.py
facade for the full re-exported surface). Leaf module in the read_models_*
DAG — no sibling imports. Holds the core/fact table constants, the three
execution_events-derived view SQL fragments (decision/outcome/attention),
COMPONENT_TABLES, ScopeFilter, and the generic connect/scope/row helpers
every other read_models_* sibling depends on.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from core.config.database import get_db_path
from core.findings.current_status import FINDINGS_CURRENT_STATUS_SQL

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
    # findings_current_status: dropped migration 140 (WO dff23cb0) — findings
    # are derived from security_events at read time (see
    # core/findings/current_status.py); security_events is the required table.
    "security_events",
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


@dataclass(frozen=True)
class ScopeFilter:
    project_id: str | None = None
    milestone_id: str | None = None
    task_id: str | None = None
    process_run_id: str | None = None


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
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat()
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


def _security_finding_row_count(conn: sqlite3.Connection, scope: ScopeFilter | None = None) -> int:
    """Like _row_count, but over the security_events-derived findings view
    (findings_current_status dropped migration 140, WO dff23cb0 — see
    core/findings/current_status.py)."""
    where, params = _where_scope(scope)
    return int(
        conn.execute(
            f"SELECT COUNT(*) FROM ({FINDINGS_CURRENT_STATUS_SQL}) {where}", params
        ).fetchone()[0]
        or 0
    )


def _analytics_rows(sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    """Read rows from the DuckDB analytics store (events_fact + views), read-only.

    Fail-open: returns [] if the store, schema, or view is unavailable (fresh
    install with no aggregate_metrics.db yet, or DuckDB not importable) so a
    dashboard read never raises. The analytics store is NEVER-AUTHORITY.
    """
    try:
        from core.analytics.duckdb_store import connect_analytics
    except Exception:
        return []
    conn = None
    try:
        conn = connect_analytics(read_only=True)
        cur = conn.execute(sql, list(params))
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]
    except Exception:
        return []
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


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
