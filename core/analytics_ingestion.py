"""Analytics-only normalized ingestion contracts.

This module lets the analytics-only profile import externally produced facts
into current SQLite authority without depending on hooks, agents, workflows,
Claude, Codex, Docker, repo mutation, or full orchestration.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ANALYTICS_INGESTION_SCHEMA = "dream_studio.analytics_only_ingestion.v1"

INGESTION_SECTIONS: tuple[str, ...] = (
    "projects",
    "validations",
    "findings",
    "token_usage",
    "ai_usage",
    "components",
    "dependencies",
    "readiness_assessments",
)

SECTION_TABLES: dict[str, tuple[str, ...]] = {
    "projects": ("business_projects",),
    "validations": ("validation_results",),
    "findings": ("security_events",),  # findings retired in migration 112 → security_events spine
    "token_usage": ("token_usage_records",),
    "ai_usage": ("ai_usage_operational_records",),
    "components": (),  # pi_components dropped in migration 084
    "dependencies": (),  # pi_dependencies dropped in migration 084
    "readiness_assessments": (
        "readiness_events",
    ),  # production_readiness_* dropped in migration 112
}

TABLE_KEYS: dict[str, str] = {
    "business_projects": "project_id",
    "validation_results": "validation_id",
    "security_events": "event_id",
    "token_usage_records": "token_usage_id",
    "ai_usage_operational_records": "usage_record_id",
    "readiness_events": "event_id",
}

# These tables are append-only event spines — never update existing rows on re-import.
APPEND_ONLY_TABLES: frozenset[str] = frozenset({"security_events", "readiness_events"})

ANALYTICS_ONLY_CAPABILITIES: tuple[str, ...] = (
    "normalized_project_import",
    "ci_validation_import",
    "security_finding_import",
    "token_usage_import",
    "operational_ai_usage_import",
    "readiness_scorecard_import",
    "dashboard_api_read_models",
    "honest_empty_states",
)


def analytics_only_ingestion_contract() -> dict[str, Any]:
    """Return the analytics-only ingestion contract."""

    return {
        "schema": ANALYTICS_INGESTION_SCHEMA,
        "model_name": "analytics_only_deployment_profile_and_ingestion_contracts",
        "derived_view": True,
        "primary_authority": False,
        "profile_id": "analytics_only",
        "hooks_required": False,
        "agents_required": False,
        "workflows_required": False,
        "claude_required": False,
        "codex_required": False,
        "docker_required": False,
        "repo_mutation_required": False,
        "default_write_authorized": False,
        "write_authorization": "explicit_ingestion_execute_only",
        "hooks_are_optional_producers": True,
        "sections": [
            {
                "section": section,
                "target_tables": list(SECTION_TABLES[section]),
                "required": False,
                "empty_state": "honest_empty_state",
            }
            for section in INGESTION_SECTIONS
        ],
        "capabilities": list(ANALYTICS_ONLY_CAPABILITIES),
        "dashboard_routes": [
            "/api/v1/projects",
            "/api/v1/projects/{project_id}/details",
            "/api/v1/metrics/*",
            "/api/v1/security/*",
            "/api/shared-intelligence/analytics-only",
            "/api/shared-intelligence/production-readiness",
            "/api/shared-intelligence/ai-usage-accounting",
        ],
    }


def analytics_only_profile_status(conn: sqlite3.Connection) -> dict[str, Any]:
    """Return analytics-only table/read-model readiness without writing data."""

    tables = _table_names(conn)
    section_status = {}
    for section, target_tables in SECTION_TABLES.items():
        available = [table for table in target_tables if table in tables]
        missing = [table for table in target_tables if table not in tables]
        section_status[section] = {
            "status": "available" if available else "unavailable",
            "available_tables": available,
            "missing_tables": missing,
            "honest_empty_state": bool(missing),
        }
    return {
        **analytics_only_ingestion_contract(),
        "model_name": "dream_studio_analytics_only_profile_status",
        "section_status": section_status,
        "table_count": len(tables),
        "source_tables": sorted(
            {table for tables_ in SECTION_TABLES.values() for table in tables_}
        ),
        "dashboard_api_available": True,
        "ingestion_cli": "ds analytics-ingest --file <payload.json> --execute",
        "dry_run_cli": "ds analytics-ingest --file <payload.json>",
        "empty_state": (
            "Analytics-only routes and import contracts are available; missing facts render "
            "as honest empty states."
        ),
    }


def ingest_analytics_payload(
    conn: sqlite3.Connection,
    payload: dict[str, Any],
    *,
    execute: bool = False,
) -> dict[str, Any]:
    """Ingest a normalized analytics payload into current SQLite authority.

    Dry-run is the default. Set execute=True to write idempotent records.
    """

    if not isinstance(payload, dict):
        raise ValueError("analytics ingestion payload must be a JSON object")

    source_refs = _json_list(payload.get("source_refs"))
    evidence_refs = _json_list(payload.get("evidence_refs"))
    ingested_at = str(payload.get("ingested_at") or datetime.now(timezone.utc).isoformat())
    tables = _table_names(conn)
    written: Counter[str] = Counter()
    planned: Counter[str] = Counter()
    skipped: list[dict[str, Any]] = []

    section_handlers = {
        "projects": _project_rows,
        "validations": _validation_rows,
        "findings": _security_finding_rows,
        "token_usage": _token_usage_rows,
        "ai_usage": _ai_usage_rows,
        "components": _component_rows,
        "dependencies": _dependency_rows,
        "readiness_assessments": _readiness_rows,
    }

    for section in INGESTION_SECTIONS:
        records = payload.get(section) or []
        if not isinstance(records, list):
            skipped.append(
                {
                    "section": section,
                    "reason": "section_is_not_a_list",
                    "target_tables": list(SECTION_TABLES[section]),
                }
            )
            continue
        missing = [table for table in SECTION_TABLES[section] if table not in tables]
        if missing:
            skipped.append(
                {
                    "section": section,
                    "reason": "target_tables_missing",
                    "missing_tables": missing,
                }
            )
            continue
        for record in records:
            if not isinstance(record, dict):
                skipped.append({"section": section, "reason": "record_is_not_an_object"})
                continue
            rows = section_handlers[section](
                record,
                source_refs=source_refs,
                evidence_refs=evidence_refs,
                ingested_at=ingested_at,
            )
            for table, row in rows:
                planned[table] += 1
                if execute:
                    _upsert(conn, table, row)
                    written[table] += 1

    if execute:
        conn.commit()
        if written.get("security_events"):
            try:
                from core.projections.findings_projection import FindingsProjection

                FindingsProjection().fold_spine(conn)
            except Exception:  # noqa: BLE001
                pass

    return {
        "schema": ANALYTICS_INGESTION_SCHEMA,
        "model_name": "dream_studio_analytics_only_ingestion_result",
        "derived_view": True,
        "primary_authority": False,
        "execute": execute,
        "dry_run": not execute,
        "db_write_authorized": execute,
        "hooks_required": False,
        "agents_required": False,
        "workflows_required": False,
        "claude_required": False,
        "codex_required": False,
        "docker_required": False,
        "repo_mutation_required": False,
        "records_planned": dict(planned),
        "records_written": dict(written),
        "skipped": skipped,
        "source_refs": source_refs,
        "evidence_refs": evidence_refs,
        "dashboard_api_consumers": analytics_only_ingestion_contract()["dashboard_routes"],
        "empty_state_policy": "missing sections are skipped and exposed as honest empty states",
    }


def load_analytics_payload(path: str | Path) -> dict[str, Any]:
    """Load a normalized analytics ingestion payload from JSON."""

    payload_path = Path(path)
    with payload_path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("analytics ingestion file must contain a JSON object")
    refs = _json_list(payload.get("source_refs"))
    payload["source_refs"] = [*refs, f"file:{payload_path.resolve()}"]
    return payload


def _project_rows(
    record: dict[str, Any],
    *,
    source_refs: list[str],
    evidence_refs: list[str],
    ingested_at: str,
) -> list[tuple[str, dict[str, Any]]]:
    project_id = _required(record, "project_id")
    stack = record.get("stack_json")
    if isinstance(stack, (dict, list)):
        stack = _json(stack)
    # reg_projects deleted in migration 084; write to business_projects.
    # Analysis columns (stack_detected, health_score, etc.) not present in business_projects;
    # they are dropped along with the reg_projects bolt-on. Ingest the core identity fields only.
    return [
        (
            "business_projects",
            {
                "project_id": project_id,
                "name": record.get("project_name") or project_id,
                "description": record.get("description") or "",
                "status": record.get("status") or "active",
                "project_path": record.get("project_path"),
                "total_sessions": _int(record.get("total_sessions"), 0),
                "total_tokens": _int(record.get("total_tokens"), 0),
                "last_session_at": record.get("last_session_at"),
                "created_at": record.get("created_at") or ingested_at,
                "updated_at": ingested_at,
            },
        )
    ]


def _validation_rows(
    record: dict[str, Any],
    *,
    source_refs: list[str],
    evidence_refs: list[str],
    ingested_at: str,
) -> list[tuple[str, dict[str, Any]]]:
    project_id = _required(record, "project_id")
    validation_id = record.get("validation_id") or _stable_id("validation", record)
    return [
        (
            "validation_results",
            {
                "validation_id": validation_id,
                "project_id": project_id,
                "milestone_id": record.get("milestone_id"),
                "task_id": record.get("task_id"),
                "process_run_id": record.get("process_run_id"),
                "event_id": record.get("event_id"),
                "validation_type": record.get("validation_type") or "analytics_import",
                "status": record.get("status") or "unknown",
                "command": record.get("command"),
                "scope": record.get("scope"),
                "summary": record.get("summary"),
                "evidence_refs_json": _json(_merged_refs(record, evidence_refs)),
                "created_at": record.get("created_at") or ingested_at,
            },
        )
    ]


def _security_finding_rows(
    record: dict[str, Any],
    *,
    source_refs: list[str],
    evidence_refs: list[str],
    ingested_at: str,
) -> list[tuple[str, dict[str, Any]]]:
    # findings table retired in migration 112; write to security_events spine instead.
    project_id = _required(record, "project_id")
    event_id = record.get("finding_id") or _stable_id("security", record)
    rule_id = record.get("rule_id") or record.get("control_id")
    description = record.get("description") or record.get("summary") or ""
    recommendation = record.get("recommendation") or record.get("remediation_path") or ""
    body_parts = [description]
    if recommendation:
        body_parts.append(f"Remediation: {recommendation}")
    if rule_id:
        body_parts.append(f"Rule: {rule_id}")
    return [
        (
            "security_events",
            {
                "event_id": event_id,
                "event_kind": "finding.recorded",
                "project_id": project_id,
                "work_order_id": record.get("work_order_id"),
                "severity": record.get("severity") or "unknown",
                "vuln_class": record.get("category") or record.get("control_family") or "imported",
                "file_path": record.get("file_path"),
                "line_number": record.get("line") or record.get("start_line"),
                "title": rule_id or record.get("category") or "analytics_import",
                "body": "\n".join(body_parts).strip() or None,
                "created_at": record.get("created_at") or ingested_at,
            },
        )
    ]


def _token_usage_rows(
    record: dict[str, Any],
    *,
    source_refs: list[str],
    evidence_refs: list[str],
    ingested_at: str,
) -> list[tuple[str, dict[str, Any]]]:
    token_id = record.get("token_usage_id") or _stable_id("token", record)
    input_tokens = _int(record.get("input_tokens"), 0)
    output_tokens = _int(record.get("output_tokens"), 0)
    cached_tokens = _int(record.get("cached_tokens"), 0)
    total_tokens = _int(record.get("total_tokens"), input_tokens + output_tokens + cached_tokens)
    cost_visibility = record.get("cost_visibility") or "unavailable"
    cost_source = record.get("cost_source") or "unavailable"
    cost_allowed = cost_visibility in {
        "exact",
        "provider_reported",
        "estimated",
        "allocated_subscription_cost",
    } and cost_source not in {"unknown", "unavailable"}
    return [
        (
            "token_usage_records",
            {
                "token_usage_id": token_id,
                "project_id": record.get("project_id"),
                "milestone_id": record.get("milestone_id"),
                "task_id": record.get("task_id"),
                "process_run_id": record.get("process_run_id"),
                "agent_id": record.get("agent_id"),
                "skill_id": record.get("skill_id"),
                "workflow_id": record.get("workflow_id"),
                "hook_id": record.get("hook_id"),
                "model_id": record.get("model_id"),
                "provider": record.get("provider"),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cached_tokens": cached_tokens,
                "total_tokens": total_tokens,
                "estimated_cost": record.get("cost_amount") if cost_allowed else 0,
                "purpose": record.get("purpose") or "analytics_only_import",
                "created_at": record.get("created_at") or ingested_at,
                "source_refs_json": _json(_merged_refs(record, source_refs, key="source_refs")),
                "evidence_refs_json": _json(_merged_refs(record, evidence_refs)),
                "adapter_id": record.get("adapter_id"),
                "billing_mode": record.get("billing_mode") or "unknown",
                "token_visibility": record.get("token_visibility") or "exact",
                "cost_visibility": cost_visibility,
                "usage_source": record.get("usage_source") or "local_telemetry",
                "cost_source": cost_source,
                "accounting_confidence": record.get("confidence")
                or record.get("accounting_confidence")
                or "medium",
            },
        )
    ]


def _ai_usage_rows(
    record: dict[str, Any],
    *,
    source_refs: list[str],
    evidence_refs: list[str],
    ingested_at: str,
) -> list[tuple[str, dict[str, Any]]]:
    usage_id = record.get("usage_record_id") or _stable_id("ai-usage", record)
    cost_visibility = record.get("cost_visibility") or "unknown"
    cost_source = record.get("cost_source") or "unknown"
    cost_allowed = cost_visibility in {
        "exact",
        "provider_reported",
        "estimated",
        "allocated_subscription_cost",
    } and cost_source not in {"unknown", "unavailable"}
    return [
        (
            "ai_usage_operational_records",
            {
                "usage_record_id": usage_id,
                "project_id": record.get("project_id"),
                "milestone_id": record.get("milestone_id"),
                "task_id": record.get("task_id"),
                "work_order_id": record.get("work_order_id"),
                "process_run_id": record.get("process_run_id"),
                "adapter_id": record.get("adapter_id") or "unknown",
                "provider": record.get("provider"),
                "model_id": record.get("model_id"),
                "accounting_profile_id": record.get("accounting_profile_id"),
                "token_usage_id": record.get("token_usage_id"),
                "billing_mode": record.get("billing_mode") or "unknown",
                "token_visibility": record.get("token_visibility") or "unavailable",
                "cost_visibility": cost_visibility,
                "usage_source": record.get("usage_source") or "local_telemetry",
                "cost_source": cost_source,
                "confidence": record.get("confidence") or "unknown",
                "input_tokens": record.get("input_tokens"),
                "output_tokens": record.get("output_tokens"),
                "cached_tokens": record.get("cached_tokens"),
                "total_tokens": record.get("total_tokens"),
                "cost_amount": record.get("cost_amount") if cost_allowed else None,
                "cost_currency": record.get("cost_currency") if cost_allowed else None,
                "run_count": _int(record.get("run_count"), 1),
                "files_touched_json": _json(_json_list(record.get("files_touched"))),
                "commands_run_json": _json(_json_list(record.get("commands_run"))),
                "validation_result": record.get("validation_result"),
                "pr_result_outcome": record.get("pr_result_outcome"),
                "success": _bool_or_none(record.get("success")),
                "failure_reason": record.get("failure_reason"),
                "rework_needed": _bool_or_none(record.get("rework_needed")),
                "security_findings_json": _json(_json_list(record.get("security_findings"))),
                "readiness_findings_json": _json(_json_list(record.get("readiness_findings"))),
                "duration_ms": record.get("duration_ms"),
                "source_refs_json": _json(_merged_refs(record, source_refs, key="source_refs")),
                "evidence_refs_json": _json(_merged_refs(record, evidence_refs)),
                "created_at": record.get("created_at") or ingested_at,
            },
        )
    ]


def _dependency_rows(
    record: dict[str, Any],
    *,
    source_refs: list[str],
    evidence_refs: list[str],
    ingested_at: str,
) -> list[tuple[str, dict[str, Any]]]:
    # pi_dependencies dropped in migration 084 — no-op.
    return []


def _component_rows(
    record: dict[str, Any],
    *,
    source_refs: list[str],
    evidence_refs: list[str],
    ingested_at: str,
) -> list[tuple[str, dict[str, Any]]]:
    # pi_components dropped in migration 084 — no-op.
    return []


def _readiness_rows(
    record: dict[str, Any],
    *,
    source_refs: list[str],
    evidence_refs: list[str],
    ingested_at: str,
) -> list[tuple[str, dict[str, Any]]]:
    # production_readiness_* tables retired in migration 112; write to readiness_events spine.
    project_id = _required(record, "project_id")
    assessment_id = record.get("assessment_id") or _stable_id("readiness", record)
    status = record.get("status") or "partial"
    confidence = record.get("confidence") or "medium"
    body = _json(
        {
            "status": status,
            "confidence": confidence,
            "health_score": record.get("health_score"),
            "readiness_score": record.get("readiness_score"),
            "missing_evidence": _json_list(record.get("missing_evidence")),
            "blocking_factors": _json_list(record.get("blocking_factors")),
            "release_readiness_effect": record.get("release_readiness_effect"),
        }
    )
    rows: list[tuple[str, dict[str, Any]]] = [
        (
            "readiness_events",
            {
                "event_id": assessment_id,
                "event_kind": "assessment.started",
                "project_id": project_id,
                "work_order_id": record.get("work_order_id"),
                "title": f"analytics import: {assessment_id}",
                "body": body,
                "created_at": record.get("created_at") or ingested_at,
            },
        )
    ]
    for control in record.get("controls") or []:
        if not isinstance(control, dict):
            continue
        control_id = control.get("control_id") or "unknown_control"
        result_id = control.get("result_id") or _stable_id("readiness-control", control)
        result = control.get("status") or "incomplete"
        rows.append(
            (
                "readiness_events",
                {
                    "event_id": result_id,
                    "parent_event_id": assessment_id,
                    "event_kind": "control_result.recorded",
                    "project_id": project_id,
                    "control_id": control_id,
                    "result": result,
                    "title": control_id,
                    "body": _json(
                        {
                            "control_family": control.get("control_family"),
                            "severity": control.get("severity"),
                            "applicability": control.get("applicability"),
                        }
                    ),
                    "created_at": control.get("created_at") or ingested_at,
                },
            )
        )
    return rows


def _upsert(conn: sqlite3.Connection, table: str, row: dict[str, Any]) -> None:
    columns = _table_columns(conn, table)
    filtered = {key: value for key, value in row.items() if key in columns}
    if not filtered:
        return
    col_sql = ", ".join(filtered)
    placeholders = ", ".join("?" for _ in filtered)
    if table in APPEND_ONLY_TABLES:
        # Event spines are append-only — INSERT OR IGNORE on duplicate PK for idempotent re-import.
        conn.execute(
            f"INSERT OR IGNORE INTO {table}({col_sql}) VALUES ({placeholders})",
            tuple(filtered.values()),
        )
        return
    key = TABLE_KEYS.get(table)
    if key and key in filtered:
        update_columns = [column for column in filtered if column != key]
        if update_columns:
            set_sql = ", ".join(f"{column} = ?" for column in update_columns)
            values = [filtered[column] for column in update_columns]
            values.append(filtered[key])
            cursor = conn.execute(
                f"UPDATE {table} SET {set_sql} WHERE {key} = ?",
                tuple(values),
            )
            if cursor.rowcount:
                return
    conn.execute(
        f"INSERT INTO {table}({col_sql}) VALUES ({placeholders})",
        tuple(filtered.values()),
    )


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        ).fetchall()
    }


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _required(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if not value:
        raise ValueError(f"analytics ingestion record missing required field: {key}")
    return str(value)


def _stable_id(prefix: str, record: dict[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}-{digest}"


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        return [value]
    return [value]


def _merged_refs(
    record: dict[str, Any],
    inherited: list[str],
    *,
    key: str = "evidence_refs",
) -> list[Any]:
    refs = [*inherited, *_json_list(record.get(key))]
    return list(dict.fromkeys(refs))


def _int(value: Any, default: int) -> int:
    if value is None:
        return default
    return int(value)


def _score(value: Any) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    if numeric > 1.0:
        numeric = numeric / 100.0
    return max(0.0, min(1.0, numeric))


def _bool_or_none(value: Any) -> int | None:
    if value is None:
        return None
    return int(bool(value))
