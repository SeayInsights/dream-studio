"""Per-section record shaping for analytics ingestion.

WO-GF-READINESS-INSIGHTS: split from ``core/analytics_ingestion.py``. Holds the
eight ``_<section>_rows`` handlers and their record-shaping helpers. No logic
changes — extracted verbatim.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .analytics_ingestion_shared import _json_list


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
