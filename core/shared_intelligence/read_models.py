"""Derived read models for shared-intelligence learning records.

These read models consume SQLite authority tables created by migration 038.
They are read-only projections for dashboards, routing, and future context
packets; they do not mutate SQLite and they do not make files authoritative.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from core.shared_intelligence.authority import require_shared_intelligence_tables

LEARNING_SOURCE_TABLES: tuple[str, ...] = (
    "learning_event_records",
    "hardening_candidate_records",
)

SEVERITY_RANK: dict[str, int] = {
    "critical": 5,
    "high": 4,
    "medium": 3,
    "warning": 2,
    "low": 1,
    "info": 0,
}


def learning_event_summary(
    conn: sqlite3.Connection,
    *,
    project_id: str | None = None,
    milestone_id: str | None = None,
    task_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Return a dashboard-safe summary of observed learning events."""

    require_shared_intelligence_tables(conn)
    scope_filter, params = _scope_filter(project_id, milestone_id, task_id, alias="le")
    events = _learning_events(conn, scope_filter, params, limit)
    hardening = _hardening_candidates(conn, scope_filter, params)

    class_counts = Counter(str(event["event_class"]) for event in events)
    severity_counts = Counter(str(event["severity"]) for event in events)
    promotion_counts = Counter(str(event["promotion_status"]) for event in events)
    recurrence_counts = Counter(
        str(event["recurrence_key"]) for event in events if event.get("recurrence_key")
    )

    return _with_authority(
        "shared_intelligence_learning_event_summary",
        {
            "scope": {
                "project_id": project_id,
                "milestone_id": milestone_id,
                "task_id": task_id,
            },
            "event_count": len(events),
            "event_class_counts": dict(sorted(class_counts.items())),
            "severity_counts": dict(sorted(severity_counts.items())),
            "promotion_status_counts": dict(sorted(promotion_counts.items())),
            "recurrence_signals": [
                {"recurrence_key": key, "event_count": count}
                for key, count in sorted(
                    recurrence_counts.items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ],
            "operator_approval_items": [
                event
                for event in events
                if event["promotion_status"] == "operator_approval_required"
            ],
            "dashboard_attention_items": [
                event for event in events if event["promotion_status"] == "dashboard_attention"
            ],
            "candidate_events": [
                event for event in events if event["promotion_status"] == "candidate"
            ],
            "hardening_candidates": hardening,
            "recent_events": events,
            "empty_state": "No learning events recorded for the selected scope.",
        },
    )


def component_learning_health(
    conn: sqlite3.Connection,
    *,
    project_id: str | None = None,
    milestone_id: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Group learning events and hardening candidates by component."""

    require_shared_intelligence_tables(conn)
    scope_filter, params = _scope_filter(project_id, milestone_id, task_id, alias="le")
    events = _learning_events(conn, scope_filter, params, limit=100)
    hardening = _hardening_candidates(conn, scope_filter, params)

    by_component: dict[tuple[str, str], dict[str, Any]] = {}
    for event in events:
        component_type = event.get("component_type") or "unattributed"
        component_id = event.get("component_id") or "unknown"
        key = (str(component_type), str(component_id))
        row = by_component.setdefault(
            key,
            {
                "component_type": component_type,
                "component_id": component_id,
                "event_count": 0,
                "event_class_counts": Counter(),
                "severity_counts": Counter(),
                "promotion_status_counts": Counter(),
                "recurrence_keys": set(),
                "highest_severity": "info",
                "latest_event_at": None,
                "hardening_candidates": [],
            },
        )
        row["event_count"] += 1
        row["event_class_counts"][event["event_class"]] += 1
        row["severity_counts"][event["severity"]] += 1
        row["promotion_status_counts"][event["promotion_status"]] += 1
        if event.get("recurrence_key"):
            row["recurrence_keys"].add(event["recurrence_key"])
        if _severity_score(event["severity"]) > _severity_score(row["highest_severity"]):
            row["highest_severity"] = event["severity"]
        if row["latest_event_at"] is None or str(event["created_at"]) > str(row["latest_event_at"]):
            row["latest_event_at"] = event["created_at"]

    for candidate in hardening:
        key = (str(candidate["component_type"]), str(candidate["component_id"]))
        row = by_component.setdefault(
            key,
            {
                "component_type": candidate["component_type"],
                "component_id": candidate["component_id"],
                "event_count": 0,
                "event_class_counts": Counter(),
                "severity_counts": Counter(),
                "promotion_status_counts": Counter(),
                "recurrence_keys": set(),
                "highest_severity": "info",
                "latest_event_at": None,
                "hardening_candidates": [],
            },
        )
        row["hardening_candidates"].append(candidate)

    components = []
    for row in by_component.values():
        components.append(
            {
                "component_type": row["component_type"],
                "component_id": row["component_id"],
                "event_count": row["event_count"],
                "event_class_counts": dict(sorted(row["event_class_counts"].items())),
                "severity_counts": dict(sorted(row["severity_counts"].items())),
                "promotion_status_counts": dict(sorted(row["promotion_status_counts"].items())),
                "recurrence_keys": sorted(row["recurrence_keys"]),
                "highest_severity": row["highest_severity"],
                "latest_event_at": row["latest_event_at"],
                "hardening_candidate_count": len(row["hardening_candidates"]),
                "hardening_candidates": row["hardening_candidates"],
            }
        )

    components.sort(
        key=lambda row: (
            -_severity_score(row["highest_severity"]),
            -int(row["event_count"]),
            str(row["component_type"]),
            str(row["component_id"]),
        )
    )

    return _with_authority(
        "shared_intelligence_component_learning_health",
        {
            "scope": {
                "project_id": project_id,
                "milestone_id": milestone_id,
                "task_id": task_id,
            },
            "components": components,
            "empty_state": "No component learning events or hardening candidates recorded.",
        },
    )


def learning_promotion_queue(
    conn: sqlite3.Connection,
    *,
    project_id: str | None = None,
    milestone_id: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Return learning events grouped by promotion path."""

    require_shared_intelligence_tables(conn)
    scope_filter, params = _scope_filter(project_id, milestone_id, task_id, alias="le")
    events = _learning_events(conn, scope_filter, params, limit=100)
    hardening = _hardening_candidates(conn, scope_filter, params)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        grouped[str(event["promotion_status"])].append(event)

    return _with_authority(
        "shared_intelligence_learning_promotion_queue",
        {
            "scope": {
                "project_id": project_id,
                "milestone_id": milestone_id,
                "task_id": task_id,
            },
            "promotion_paths": dict(sorted(grouped.items())),
            "hardening_candidates": hardening,
            "operator_approval_required": grouped.get("operator_approval_required", []),
            "dashboard_attention": grouped.get("dashboard_attention", []),
            "candidate": grouped.get("candidate", []),
            "empty_state": "No learning events are awaiting promotion.",
        },
    )


def _learning_events(
    conn: sqlite3.Connection,
    scope_filter: str,
    params: list[Any],
    limit: int,
) -> list[dict[str, Any]]:
    # learning_event_records dropped migration 131 — return empty gracefully
    bounded_limit = max(1, min(int(limit), 100))
    try:
        rows = conn.execute(
            f"""
            SELECT
                le.learning_event_id,
                le.project_id,
                le.milestone_id,
                le.task_id,
                le.process_run_id,
                le.component_type,
                le.component_id,
                le.event_class,
                le.severity,
                le.summary,
                le.observed_pattern,
                le.root_cause,
                le.remediation_hint,
                le.recurrence_key,
                le.promotion_status,
                le.source_refs_json,
                le.evidence_refs_json,
                le.metadata_json,
                le.created_at
            FROM learning_event_records le
            {scope_filter}
            ORDER BY le.created_at DESC, le.learning_event_id DESC
            LIMIT ?
            """,
            (*params, bounded_limit),
        ).fetchall()
    except Exception:
        return []
    return [_decode_learning_event(row) for row in rows]


def _hardening_candidates(
    conn: sqlite3.Connection,
    scope_filter: str,
    params: list[Any],
) -> list[dict[str, Any]]:
    # hardening_candidate_records dropped migration 131 — return empty gracefully
    try:
        rows = conn.execute(
            f"""
            SELECT
                hc.candidate_id,
                hc.learning_event_id,
                hc.component_type,
                hc.component_id,
                hc.current_version,
                hc.proposed_version,
                hc.hardening_type,
                hc.status,
                hc.validation_plan_json,
                hc.recurrence_check_json,
                hc.rollback_plan,
                hc.source_refs_json,
                hc.evidence_refs_json,
                hc.created_at,
                hc.updated_at
            FROM hardening_candidate_records hc
            LEFT JOIN learning_event_records le
              ON le.learning_event_id = hc.learning_event_id
            {scope_filter}
            ORDER BY hc.updated_at DESC, hc.candidate_id DESC
            """,
            tuple(params),
        ).fetchall()
    except Exception:
        return []
    return [_decode_hardening_candidate(row) for row in rows]


def _scope_filter(
    project_id: str | None,
    milestone_id: str | None,
    task_id: str | None,
    *,
    alias: str,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if project_id is not None:
        clauses.append(f"{alias}.project_id = ?")
        params.append(project_id)
    if milestone_id is not None:
        clauses.append(f"{alias}.milestone_id = ?")
        params.append(milestone_id)
    if task_id is not None:
        clauses.append(f"{alias}.task_id = ?")
        params.append(task_id)
    if not clauses:
        return "", params
    return "WHERE " + " AND ".join(clauses), params


def _decode_learning_event(row: sqlite3.Row) -> dict[str, Any]:
    event = dict(row)
    event["source_refs"] = _loads(event.pop("source_refs_json"), [])
    event["evidence_refs"] = _loads(event.pop("evidence_refs_json"), [])
    event["metadata"] = _loads(event.pop("metadata_json"), {})
    return event


def _decode_hardening_candidate(row: sqlite3.Row) -> dict[str, Any]:
    candidate = dict(row)
    candidate["validation_plan"] = _loads(candidate.pop("validation_plan_json"), [])
    candidate["recurrence_check"] = _loads(candidate.pop("recurrence_check_json"), {})
    candidate["source_refs"] = _loads(candidate.pop("source_refs_json"), [])
    candidate["evidence_refs"] = _loads(candidate.pop("evidence_refs_json"), [])
    return candidate


def _loads(raw: str | None, default: Any) -> Any:
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _severity_score(severity: str | None) -> int:
    return SEVERITY_RANK.get(str(severity or "info").lower(), 0)


def _with_authority(model_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_name": model_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "source_tables": list(LEARNING_SOURCE_TABLES),
        "module_available": True,
        **payload,
    }
