from __future__ import annotations
import json
import sqlite3
import uuid
from typing import Any

PROJECTED_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "execution.started",
        "execution.completed",
        "execution.failed",
    }
)

_PAYLOAD_META_EXCLUDE: frozenset[str] = frozenset(
    {
        "event_name",
        "source_refs",
        "evidence_refs",
        "outcome_status",
    }
)


def apply(event_data: dict[str, Any], conn: sqlite3.Connection) -> bool:
    """Project a canonical event to execution_events if it is an execution event.

    Idempotent: replaying the same event_id is a no-op.
    Returns True if a row was written, False otherwise.
    """
    event_type = event_data.get("event_type", "")
    if event_type not in PROJECTED_EVENT_TYPES:
        return False

    source_event_id = event_data.get("event_id")
    if not source_event_id:
        return False

    try:
        existing = conn.execute(
            "SELECT 1 FROM execution_events WHERE _built_from_event_id = ?",
            (source_event_id,),
        ).fetchone()
        if existing:
            return False
    except sqlite3.OperationalError:
        # _built_from_event_id column may not exist yet on very old DBs; skip
        return False

    trace = event_data.get("trace") or {}
    payload = event_data.get("payload") or {}

    metadata = {k: v for k, v in payload.items() if k not in _PAYLOAD_META_EXCLUDE}

    conn.execute(
        """
        INSERT INTO execution_events (
            event_id, event_type, event_name, project_id, milestone_id, task_id,
            process_run_id, actor_type, actor_id, agent_id, skill_id, workflow_id,
            hook_id, tool_id, model_id, adapter_id,
            source_refs_json, evidence_refs_json, metadata_json,
            outcome_status, _built_from_event_id
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            str(uuid.uuid4()),
            event_type,
            payload.get("event_name") or event_type,
            trace.get("project_id"),
            trace.get("milestone_id"),
            trace.get("task_id"),
            trace.get("process_run_id"),
            trace.get("actor_type"),
            trace.get("actor_id"),
            trace.get("agent_id"),
            trace.get("skill_id"),
            trace.get("workflow_id"),
            trace.get("hook_id"),
            trace.get("tool_id"),
            trace.get("model_id"),
            trace.get("adapter_id"),
            json.dumps(payload.get("source_refs") or []),
            json.dumps(payload.get("evidence_refs") or []),
            json.dumps(metadata),
            payload.get("outcome_status"),
            source_event_id,
        ),
    )
    return True
