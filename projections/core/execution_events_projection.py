from __future__ import annotations
import json
import re
import sqlite3
import uuid
from pathlib import Path
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


# ── Project-attribution backfill (WO-ATTRIBUTION-NORMALIZE) ───────────────────
# execution_events is owned by this projection, so its remap writer lives here
# (single-writer ownership). Resolution logic is the pure helper in
# core.projects.attribution; the WRITE stays in the owning module.


def backfill_execution_events(conn: sqlite3.Connection) -> dict[str, int]:
    """Remap resolvable free-text project keys in execution_events to UUIDs.

    Only updates rows whose project_id is a confidently-resolvable key (matches a
    business_projects name, slug, or path basename). Already-UUID values and
    unresolvable garbage keys are left untouched. Returns {key: rows_updated}.
    """
    from core.projects.attribution import resolve_project_uuid

    try:
        raw_keys = conn.execute(
            "SELECT DISTINCT project_id FROM execution_events WHERE project_id IS NOT NULL"
        ).fetchall()
    except sqlite3.OperationalError:
        return {}

    summary: dict[str, int] = {}
    uuid_pat = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    for row in raw_keys:
        key = row[0] if isinstance(row, tuple) else row["project_id"]
        if not key or re.match(uuid_pat, key, re.IGNORECASE):
            continue
        resolved = resolve_project_uuid(key, conn)
        if resolved is None or resolved == key:
            continue
        count = conn.execute(
            "SELECT COUNT(*) FROM execution_events WHERE project_id = ?", (key,)
        ).fetchone()[0]
        if count > 0:
            conn.execute(
                "UPDATE execution_events SET project_id = ? WHERE project_id = ?",
                (resolved, key),
            )
            summary[key] = count
    return summary


def run_live_backfill(db_path: Path) -> dict[str, int]:
    """Connect to the live authority DB and run the backfill (commits on success)."""
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        summary = backfill_execution_events(conn)
        conn.commit()
        return summary
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
