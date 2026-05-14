"""Non-executing hardening loop helpers for shared intelligence records."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from core.shared_intelligence.authority import (
    record_hardening_candidate,
    require_shared_intelligence_tables,
)

ALLOWED_HARDENING_STATUSES: frozenset[str] = frozenset(
    {
        "candidate",
        "approved_for_rehearsal",
        "validated",
        "promoted",
        "rejected",
        "deferred",
    }
)


def create_hardening_candidate_from_learning_event(
    conn: sqlite3.Connection,
    *,
    candidate_id: str,
    learning_event_id: str,
    hardening_type: str,
    proposed_version: str,
    validation_plan: list[str],
    rollback_plan: str,
    current_version: str | None = None,
    source_refs: list[str] | None = None,
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    """Create a candidate from a learning event without executing hardening."""

    require_shared_intelligence_tables(conn)
    event = _learning_event(conn, learning_event_id)
    if event is None:
        raise ValueError(f"unknown learning_event_id: {learning_event_id}")
    if not event.get("component_type") or not event.get("component_id"):
        raise ValueError("learning event must identify component_type and component_id")

    recurrence_key = event.get("recurrence_key")
    recurrence_check = {
        "learning_event_id": learning_event_id,
        "recurrence_key": recurrence_key,
        "recurrence_event_count": _recurrence_event_count(conn, event),
        "component_type": event["component_type"],
        "component_id": event["component_id"],
        "execution_authorized": False,
    }
    record_hardening_candidate(
        conn,
        candidate_id=candidate_id,
        learning_event_id=learning_event_id,
        component_type=event["component_type"],
        component_id=event["component_id"],
        current_version=current_version,
        proposed_version=proposed_version,
        hardening_type=hardening_type,
        status="candidate",
        validation_plan=validation_plan,
        recurrence_check=recurrence_check,
        rollback_plan=rollback_plan,
        source_refs=source_refs or event.get("source_refs", []),
        evidence_refs=evidence_refs or event.get("evidence_refs", []),
    )
    conn.execute(
        """
        UPDATE learning_event_records
        SET promotion_status = 'candidate'
        WHERE learning_event_id = ?
          AND promotion_status = 'observed'
        """,
        (learning_event_id,),
    )
    return hardening_candidate_lifecycle(conn, candidate_id)


def record_hardening_validation(
    conn: sqlite3.Connection,
    *,
    candidate_id: str,
    status: str,
    validation_refs: list[str],
    evidence_refs: list[str] | None = None,
    validation_summary: str | None = None,
) -> dict[str, Any]:
    """Record candidate validation state without promoting or executing it."""

    require_shared_intelligence_tables(conn)
    if status not in ALLOWED_HARDENING_STATUSES:
        raise ValueError(f"unsupported hardening status: {status}")
    candidate = _hardening_candidate(conn, candidate_id)
    if candidate is None:
        raise ValueError(f"unknown candidate_id: {candidate_id}")

    recurrence_check = _loads(candidate["recurrence_check_json"], {})
    recurrence_check["validation_refs"] = validation_refs
    recurrence_check["validation_summary"] = validation_summary
    recurrence_check["execution_authorized"] = False

    merged_evidence = list(
        dict.fromkeys([*_loads(candidate["evidence_refs_json"], []), *(evidence_refs or [])])
    )
    conn.execute(
        """
        UPDATE hardening_candidate_records
        SET status = ?,
            recurrence_check_json = ?,
            evidence_refs_json = ?,
            updated_at = datetime('now')
        WHERE candidate_id = ?
        """,
        (
            status,
            json.dumps(recurrence_check, sort_keys=True),
            json.dumps(merged_evidence, sort_keys=True),
            candidate_id,
        ),
    )
    return hardening_candidate_lifecycle(conn, candidate_id)


def hardening_candidate_lifecycle(
    conn: sqlite3.Connection,
    candidate_id: str,
) -> dict[str, Any]:
    """Return a recurrence-aware lifecycle view for one hardening candidate."""

    require_shared_intelligence_tables(conn)
    candidate = _hardening_candidate(conn, candidate_id)
    if candidate is None:
        raise ValueError(f"unknown candidate_id: {candidate_id}")
    candidate_decoded = _decode_candidate(candidate)
    event = (
        _learning_event(conn, str(candidate["learning_event_id"]))
        if candidate["learning_event_id"]
        else None
    )
    recurrence_events = _recurrence_events(conn, event, candidate_decoded)

    return {
        "model_name": "shared_intelligence_hardening_candidate_lifecycle",
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "source_tables": ["learning_event_records", "hardening_candidate_records"],
        "candidate": candidate_decoded,
        "learning_event": event,
        "recurrence_events": recurrence_events,
        "recurrence_event_count": len(recurrence_events),
        "recurrence_detected": len(recurrence_events) > 1,
        "execution_authorized": False,
        "requires_future_work_order": candidate_decoded["status"]
        in {"candidate", "approved_for_rehearsal"},
        "operator_approval_required": candidate_decoded["status"] == "approved_for_rehearsal",
        "empty_state": "Hardening candidate has no linked recurrence events.",
    }


def validate_hardening_loop_report(report: dict[str, Any]) -> list[str]:
    """Validate that a hardening lifecycle report stays non-executing."""

    errors: list[str] = []
    if report.get("derived_view") is not True:
        errors.append("derived_view must be true")
    if report.get("primary_authority") is not False:
        errors.append("primary_authority must be false")
    if report.get("routing_authority") is not False:
        errors.append("routing_authority must be false")
    if report.get("execution_authorized") is not False:
        errors.append("execution_authorized must be false")
    if report.get("candidate", {}).get("status") not in ALLOWED_HARDENING_STATUSES:
        errors.append("candidate status is not allowed")
    return errors


def _learning_event(conn: sqlite3.Connection, learning_event_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM learning_event_records
        WHERE learning_event_id = ?
        """,
        (learning_event_id,),
    ).fetchone()
    if row is None:
        return None
    event = dict(row)
    event["source_refs"] = _loads(event.pop("source_refs_json"), [])
    event["evidence_refs"] = _loads(event.pop("evidence_refs_json"), [])
    event["metadata"] = _loads(event.pop("metadata_json"), {})
    return event


def _hardening_candidate(conn: sqlite3.Connection, candidate_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM hardening_candidate_records
        WHERE candidate_id = ?
        """,
        (candidate_id,),
    ).fetchone()


def _decode_candidate(row: sqlite3.Row) -> dict[str, Any]:
    candidate = dict(row)
    candidate["validation_plan"] = _loads(candidate.pop("validation_plan_json"), [])
    candidate["recurrence_check"] = _loads(candidate.pop("recurrence_check_json"), {})
    candidate["source_refs"] = _loads(candidate.pop("source_refs_json"), [])
    candidate["evidence_refs"] = _loads(candidate.pop("evidence_refs_json"), [])
    return candidate


def _recurrence_event_count(conn: sqlite3.Connection, event: dict[str, Any]) -> int:
    recurrence_key = event.get("recurrence_key")
    if not recurrence_key:
        return 1
    return int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM learning_event_records
            WHERE recurrence_key = ?
              AND COALESCE(component_type, '') = COALESCE(?, '')
              AND COALESCE(component_id, '') = COALESCE(?, '')
            """,
            (recurrence_key, event.get("component_type"), event.get("component_id")),
        ).fetchone()[0]
    )


def _recurrence_events(
    conn: sqlite3.Connection,
    event: dict[str, Any] | None,
    candidate: dict[str, Any],
) -> list[dict[str, Any]]:
    recurrence_key = None
    if event:
        recurrence_key = event.get("recurrence_key")
    recurrence_key = recurrence_key or candidate.get("recurrence_check", {}).get("recurrence_key")
    if not recurrence_key:
        return [event] if event else []
    rows = conn.execute(
        """
        SELECT *
        FROM learning_event_records
        WHERE recurrence_key = ?
          AND COALESCE(component_type, '') = COALESCE(?, '')
          AND COALESCE(component_id, '') = COALESCE(?, '')
        ORDER BY created_at ASC, learning_event_id ASC
        """,
        (recurrence_key, candidate["component_type"], candidate["component_id"]),
    ).fetchall()
    return [_decode_learning_row(row) for row in rows]


def _decode_learning_row(row: sqlite3.Row) -> dict[str, Any]:
    event = dict(row)
    event["source_refs"] = _loads(event.pop("source_refs_json"), [])
    event["evidence_refs"] = _loads(event.pop("evidence_refs_json"), [])
    event["metadata"] = _loads(event.pop("metadata_json"), {})
    return event


def _loads(raw: str | None, default: Any) -> Any:
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default
