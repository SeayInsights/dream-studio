"""AI/adapter task attribution authority and dashboard read models."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from collections.abc import Mapping
from typing import Any

TASK_ATTRIBUTION_SOURCE_TABLES: tuple[str, ...] = (
    "task_attribution_records",
    "ai_usage_operational_records",
    "adapter_result_records",
    "execution_events",
    "process_runs",
    "skill_invocations",
    "workflow_invocations",
    "hook_invocations",
    "tool_invocations",
    "validation_results",
    "findings",
    "production_readiness_control_results",
)

MODEL_VISIBILITIES = {"exact", "partial", "unknown", "unavailable"}
AVAILABILITY_STATUSES = {"available", "unavailable", "partial"}
VALIDATION_STATUSES = {
    "passed",
    "failed",
    "partial",
    "not_run",
    "unknown",
    "manual_review_required",
}
OUTCOME_STATUSES = {
    "completed",
    "committed",
    "pr_opened",
    "released",
    "partial",
    "failed",
    "manual_review_required",
    "unknown",
}
SOURCE_CLASSES = {
    "dream_studio_routed",
    "adapter_reported",
    "analytics_ingest",
    "imported_manual",
    "untracked",
}
CONFIDENCE_LEVELS = {"high", "medium", "low", "unknown"}


def record_task_attribution(conn: sqlite3.Connection, **values: Any) -> None:
    """Persist a meaningful execution-unit attribution record.

    The writer intentionally stores unknown model/provider and unavailable file
    or command details as explicit values instead of inventing precision.
    """

    _require_task_attribution_table(conn)
    files_touched = values.get("files_touched")
    commands_run = values.get("commands_run")
    conn.execute(
        """
        INSERT OR REPLACE INTO task_attribution_records (
            attribution_id, project_id, milestone_id, task_id, work_order_id,
            process_run_id, event_id, adapter_id, provider, model_id,
            model_visibility, agent_id, skill_ids_json, workflow_ids_json,
            hook_ids_json, tool_ids_json, files_touched_json,
            files_touched_status, files_touched_unavailable_reason,
            commands_run_json, commands_run_status, validations_json,
            validation_status, security_impact_json, readiness_impact_json,
            outcome_status, outcome_summary, commit_refs_json, pr_refs_json,
            result_refs_json, rework_needed, rework_status, ai_usage_record_id,
            token_usage_id, adapter_result_id, source_class, confidence,
            source_refs_json, evidence_refs_json, updated_at
        ) VALUES (
            :attribution_id, :project_id, :milestone_id, :task_id, :work_order_id,
            :process_run_id, :event_id, :adapter_id, :provider, :model_id,
            :model_visibility, :agent_id, :skill_ids_json, :workflow_ids_json,
            :hook_ids_json, :tool_ids_json, :files_touched_json,
            :files_touched_status, :files_touched_unavailable_reason,
            :commands_run_json, :commands_run_status, :validations_json,
            :validation_status, :security_impact_json, :readiness_impact_json,
            :outcome_status, :outcome_summary, :commit_refs_json, :pr_refs_json,
            :result_refs_json, :rework_needed, :rework_status, :ai_usage_record_id,
            :token_usage_id, :adapter_result_id, :source_class, :confidence,
            :source_refs_json, :evidence_refs_json, datetime('now')
        )
        """,
        {
            "attribution_id": values["attribution_id"],
            "project_id": values.get("project_id"),
            "milestone_id": values.get("milestone_id"),
            "task_id": values.get("task_id"),
            "work_order_id": values.get("work_order_id"),
            "process_run_id": values.get("process_run_id"),
            "event_id": values.get("event_id"),
            "adapter_id": values["adapter_id"],
            "provider": values.get("provider") or "unknown",
            "model_id": values.get("model_id") or "unknown",
            "model_visibility": _enum(
                values.get("model_visibility"),
                MODEL_VISIBILITIES,
                "unknown",
            ),
            "agent_id": values.get("agent_id"),
            "skill_ids_json": _json(values.get("skill_ids"), []),
            "workflow_ids_json": _json(values.get("workflow_ids"), []),
            "hook_ids_json": _json(values.get("hook_ids"), []),
            "tool_ids_json": _json(values.get("tool_ids"), []),
            "files_touched_json": _json(files_touched, []),
            "files_touched_status": _availability_status(
                values.get("files_touched_status"),
                files_touched,
            ),
            "files_touched_unavailable_reason": values.get("files_touched_unavailable_reason"),
            "commands_run_json": _json(commands_run, []),
            "commands_run_status": _availability_status(
                values.get("commands_run_status"),
                commands_run,
            ),
            "validations_json": _json(values.get("validations"), []),
            "validation_status": _enum(
                values.get("validation_status"),
                VALIDATION_STATUSES,
                "unknown",
            ),
            "security_impact_json": _json(values.get("security_impact"), {}),
            "readiness_impact_json": _json(values.get("readiness_impact"), {}),
            "outcome_status": _enum(
                values.get("outcome_status"),
                OUTCOME_STATUSES,
                "manual_review_required",
            ),
            "outcome_summary": values.get("outcome_summary"),
            "commit_refs_json": _json(values.get("commit_refs"), []),
            "pr_refs_json": _json(values.get("pr_refs"), []),
            "result_refs_json": _json(values.get("result_refs"), []),
            "rework_needed": _optional_bool(values.get("rework_needed")),
            "rework_status": values.get("rework_status") or "unknown",
            "ai_usage_record_id": values.get("ai_usage_record_id"),
            "token_usage_id": values.get("token_usage_id"),
            "adapter_result_id": values.get("adapter_result_id"),
            "source_class": _enum(values.get("source_class"), SOURCE_CLASSES, "untracked"),
            "confidence": _enum(values.get("confidence"), CONFIDENCE_LEVELS, "unknown"),
            "source_refs_json": _json(values.get("source_refs"), []),
            "evidence_refs_json": _json(values.get("evidence_refs"), []),
        },
    )


def task_attribution_summary(
    conn: sqlite3.Connection,
    *,
    project_id: str | None = None,
    work_order_id: str | None = None,
    adapter_id: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Return dashboard-ready task attribution records and rollups."""

    missing = _missing_source_tables(conn)
    if "task_attribution_records" in missing:
        return _empty_summary(project_id, work_order_id, adapter_id, missing)

    records = _records(
        conn,
        project_id=project_id,
        work_order_id=work_order_id,
        adapter_id=adapter_id,
        limit=limit,
    )
    by_adapter: dict[str, Counter[str]] = defaultdict(Counter)
    by_skill: dict[str, Counter[str]] = defaultdict(Counter)
    by_workflow: dict[str, Counter[str]] = defaultdict(Counter)
    by_project_task: dict[str, Counter[str]] = defaultdict(Counter)
    validation_counts: Counter[str] = Counter()
    outcome_counts: Counter[str] = Counter()
    rework_needed_count = 0
    manual_review_count = 0

    for record in records:
        outcome = record["outcome_status"]
        validation = record["validation_status"]
        by_adapter[record["adapter_id"]][outcome] += 1
        validation_counts[validation] += 1
        outcome_counts[outcome] += 1
        if record["rework_needed"] is True:
            rework_needed_count += 1
        if outcome == "manual_review_required" or validation == "manual_review_required":
            manual_review_count += 1
        scope_key = "::".join(
            item or "unknown"
            for item in (
                record.get("project_id"),
                record.get("milestone_id"),
                record.get("task_id"),
            )
        )
        by_project_task[scope_key][outcome] += 1
        for skill_id in record.get("skill_ids", []):
            by_skill[str(skill_id)][outcome] += 1
        for workflow_id in record.get("workflow_ids", []):
            by_workflow[str(workflow_id)][outcome] += 1

    return {
        "model_name": "dream_studio_task_attribution",
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "project_id": project_id,
        "work_order_id": work_order_id,
        "adapter_id": adapter_id,
        "source_tables": list(TASK_ATTRIBUTION_SOURCE_TABLES),
        "source_status": {
            "status": "available" if not missing else "partial",
            "missing_tables": missing,
        },
        "record_count": len(records),
        "records": records,
        "summary": {
            "outcome_counts": dict(sorted(outcome_counts.items())),
            "validation_counts": dict(sorted(validation_counts.items())),
            "rework_needed_count": rework_needed_count,
            "manual_review_count": manual_review_count,
            "by_adapter": _counter_map(by_adapter),
            "by_skill": _counter_map(by_skill),
            "by_workflow": _counter_map(by_workflow),
            "by_project_milestone_task": _counter_map(by_project_task),
        },
        "policy": {
            "model_provider_unknown_is_explicit": True,
            "token_cost_precision_not_inferred": True,
            "untracked_work_marked_untracked_or_imported_manual": True,
            "files_unavailable_requires_reason": True,
            "dashboard_is_derived": True,
        },
        "empty_state": "No task attribution records exist for this scope.",
    }


def work_order_task_attribution(
    conn: sqlite3.Connection, work_order_id: str, *, limit: int = 50
) -> dict[str, Any]:
    """Return Work Order attribution detail."""

    return task_attribution_summary(conn, work_order_id=work_order_id, limit=limit)


def project_recent_attributed_work(
    conn: sqlite3.Connection, project_id: str, *, limit: int = 10
) -> dict[str, Any]:
    """Return recent attributed work for Project Details."""

    return task_attribution_summary(conn, project_id=project_id, limit=limit)


def validate_task_attribution_summary(summary: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if summary.get("derived_view") is not True:
        errors.append("derived_view must be true")
    if summary.get("primary_authority") is not False:
        errors.append("primary_authority must be false")
    for record in summary.get("records", []):
        if record.get("model_id") in {None, ""}:
            errors.append(f"record {record.get('attribution_id')} has empty model_id")
        if record.get("provider") in {None, ""}:
            errors.append(f"record {record.get('attribution_id')} has empty provider")
        if record.get("cost_amount") is not None:
            errors.append("task attribution records must not expose cost amounts")
        if record.get("files_touched_status") == "unavailable" and record.get("files_touched"):
            errors.append(f"record {record.get('attribution_id')} has files but unavailable status")
    return errors


def _records(
    conn: sqlite3.Connection,
    *,
    project_id: str | None,
    work_order_id: str | None,
    adapter_id: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    where: list[str] = []
    params: list[Any] = []
    if project_id:
        where.append("project_id = ?")
        params.append(project_id)
    if work_order_id:
        where.append("work_order_id = ?")
        params.append(work_order_id)
    if adapter_id:
        where.append("adapter_id = ?")
        params.append(adapter_id)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    params.append(int(limit))
    rows = conn.execute(
        f"""
        SELECT *
        FROM task_attribution_records
        {clause}
        ORDER BY created_at DESC, attribution_id DESC
        LIMIT ?
        """,
        tuple(params),
    ).fetchall()
    return [_decode_record(row) for row in rows]


def _decode_record(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    for key in (
        "skill_ids",
        "workflow_ids",
        "hook_ids",
        "tool_ids",
        "files_touched",
        "commands_run",
        "validations",
        "commit_refs",
        "pr_refs",
        "result_refs",
        "source_refs",
        "evidence_refs",
    ):
        record[key] = _loads(record.pop(f"{key}_json"), [])
    for key in ("security_impact", "readiness_impact"):
        record[key] = _loads(record.pop(f"{key}_json"), {})
    record["rework_needed"] = _decode_optional_bool(record.get("rework_needed"))
    record["cost_amount"] = None
    record["cost_visibility"] = "unavailable"
    record["token_visibility_note"] = (
        "Task attribution links to token/usage records but does not invent token or cost precision."
    )
    return record


def _missing_source_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN "
        f"({','.join('?' for _ in TASK_ATTRIBUTION_SOURCE_TABLES)})",
        tuple(TASK_ATTRIBUTION_SOURCE_TABLES),
    ).fetchall()
    found = {str(row[0]) for row in rows}
    return sorted(set(TASK_ATTRIBUTION_SOURCE_TABLES) - found)


def _require_task_attribution_table(conn: sqlite3.Connection) -> None:
    if "task_attribution_records" in _missing_source_tables(conn):
        raise RuntimeError("task_attribution_records schema is missing")


def _empty_summary(
    project_id: str | None,
    work_order_id: str | None,
    adapter_id: str | None,
    missing: list[str],
) -> dict[str, Any]:
    return {
        "model_name": "dream_studio_task_attribution",
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "project_id": project_id,
        "work_order_id": work_order_id,
        "adapter_id": adapter_id,
        "source_tables": list(TASK_ATTRIBUTION_SOURCE_TABLES),
        "source_status": {"status": "migration_required", "missing_tables": missing},
        "record_count": 0,
        "records": [],
        "summary": {
            "outcome_counts": {},
            "validation_counts": {},
            "rework_needed_count": 0,
            "manual_review_count": 0,
            "by_adapter": {},
            "by_skill": {},
            "by_workflow": {},
            "by_project_milestone_task": {},
        },
        "policy": {
            "model_provider_unknown_is_explicit": True,
            "token_cost_precision_not_inferred": True,
            "untracked_work_marked_untracked_or_imported_manual": True,
            "files_unavailable_requires_reason": True,
            "dashboard_is_derived": True,
        },
        "empty_state": "Task attribution requires migration 045 before records are available.",
    }


def _availability_status(raw: Any, value: Any) -> str:
    if raw in AVAILABILITY_STATUSES:
        return str(raw)
    if value:
        return "available"
    return "unavailable"


def _enum(raw: Any, allowed: set[str], default: str) -> str:
    if raw in allowed:
        return str(raw)
    return default


def _counter_map(mapping: Mapping[str, Counter[str]]) -> dict[str, dict[str, int]]:
    return {key: dict(sorted(counter.items())) for key, counter in sorted(mapping.items())}


def _optional_bool(value: Any) -> int | None:
    if value is None:
        return None
    return 1 if bool(value) else 0


def _decode_optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _json(value: Any, default: Any) -> str:
    if value is None:
        value = default
    return json.dumps(value, sort_keys=True)


def _loads(raw: str | None, default: Any) -> Any:
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default
