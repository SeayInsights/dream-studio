"""Give the rows that predate the fix a creation event, so a rebuild stops deleting them.

WO 17466550 task 2. Emitting events going forward does not reconstruct what is already
there. MEASURED on the live authority 2026-09-10, after the spawn path was fixed:

    493 of 956 work orders  (51.6%) have no `work_order.created`
    1706 of 3311 tasks      (51.5%) have no `task.created`

Both tables are projections whose default `pre_rebuild` truncates before replaying, so a
rebuild deletes every one of those rows. A rebuild is the disaster-recovery tool, which
is what makes this worth repairing rather than living with: the authority is currently in
a state where the thing you reach for after corruption destroys half the record.

WHY BACKFILL RATHER THAN TEACH `pre_rebuild` TO PRESERVE EVENT-LESS ROWS. The task
allowed either. Preserving them would keep the rows but permanently break the property
that a projection is a pure function of its events -- a rebuild would stop being a real
replay, and a corrupted row could then never be repaired BY a rebuild, because the
corruption would be preserved along with everything else. Backfill is bounded instead of
permanent: the authoring paths now emit correctly (measured: of 19 work orders created on
2026-09-10, 0 are unreconstructable), so this runs once and the invariant holds after it.

THE EVENTS SAY THEY ARE RECONSTRUCTIONS. `payload["reconstructed_from_row"]` is true and
`payload["reconstructed_at"]` records when. A synthetic event that claimed to be the
original would make the record lie about its own provenance, and the whole point of the
event substrate is that the record can be trusted about where it came from. The event
timestamp is the ROW's `created_at`, not now, so replay order matches the real history.

DRY RUN BY DEFAULT. This writes thousands of rows into the operator's authority; it
reports what it would do and changes nothing unless `apply=True`.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: Marks an event synthesised from a surviving row rather than emitted at the time.
RECONSTRUCTED_KEY = "reconstructed_from_row"

_WORK_ORDER_SQL = """
SELECT work_order_id, project_id, milestone_id, title, description, work_order_type,
       status, created_at, originating_symptom
FROM business_work_orders t
WHERE NOT EXISTS (
    SELECT 1 FROM business_canonical_events e
    WHERE e.event_type = 'work_order.created' AND e.work_order_id = t.work_order_id
)
"""

_TASK_SQL = """
SELECT task_id, work_order_id, project_id, title, description, status, created_at,
       acceptance_criteria
FROM business_tasks t
WHERE NOT EXISTS (
    SELECT 1 FROM business_canonical_events e
    WHERE e.event_type = 'task.created' AND e.task_id = t.task_id
)
"""


def _missing_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """How many rows of each kind no replay could rebuild."""
    return {
        "work_orders": conn.execute(f"SELECT COUNT(*) FROM ({_WORK_ORDER_SQL})").fetchone()[0],
        "tasks": conn.execute(f"SELECT COUNT(*) FROM ({_TASK_SQL})").fetchone()[0],
    }


def _totals(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        "work_orders": conn.execute("SELECT COUNT(*) FROM business_work_orders").fetchone()[0],
        "tasks": conn.execute("SELECT COUNT(*) FROM business_tasks").fetchone()[0],
    }


def _envelope(event_type: str, *, payload: dict[str, Any], trace: dict[str, Any], when: str):
    from canonical.events.envelope import CanonicalEventEnvelope

    return CanonicalEventEnvelope(
        event_type=event_type,
        session_id=None,
        payload=payload,
        timestamp=when,
        severity="info",
        trace={"domain": "sdlc", "attribution_status": "fully_attributed", **trace},
    ).to_dict()


def backfill(*, db_path: Path, apply: bool = False) -> dict[str, Any]:
    """Report -- and with `apply`, repair -- rows that carry no creation event.

    Returns the counts before and after, because a repair that does not say how much it
    repaired is indistinguishable from one that did nothing. Idempotent: rows that
    already have a creation event are never selected, so a second run is a no-op.
    """
    now = datetime.now(UTC).isoformat()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        totals = _totals(conn)
        before = _missing_counts(conn)
        work_orders = [dict(r) for r in conn.execute(_WORK_ORDER_SQL)]
        tasks = [dict(r) for r in conn.execute(_TASK_SQL)]
    finally:
        conn.close()

    result: dict[str, Any] = {
        "ok": True,
        "applied": apply,
        "totals": totals,
        "before": before,
        "would_write": {"work_orders": len(work_orders), "tasks": len(tasks)},
    }

    if not apply:
        result["after"] = before
        result["note"] = "Dry run — nothing was written. Re-run with --apply to emit these events."
        return result

    from spool.ingestor import _write_to_dual_canonical

    written = {"work_orders": 0, "tasks": 0}
    failures: list[str] = []

    for row in work_orders:
        payload = {
            "title": row["title"],
            "status": row["status"] or "created",
            "type": row["work_order_type"] or "",
            "description": row["description"],
            RECONSTRUCTED_KEY: True,
            "reconstructed_at": now,
        }
        if row["originating_symptom"]:
            payload["originating_symptom"] = row["originating_symptom"]
        envelope = _envelope(
            "work_order.created",
            payload=payload,
            trace={
                "project_id": row["project_id"],
                "milestone_id": row["milestone_id"],
                "work_order_id": row["work_order_id"],
            },
            when=row["created_at"] or now,
        )
        try:
            _write_to_dual_canonical(envelope, db_path)
            written["work_orders"] += 1
        except Exception as exc:  # noqa: BLE001 - one bad row must not abandon the rest
            failures.append(f"work_order {row['work_order_id']}: {type(exc).__name__}: {exc}")

    for row in tasks:
        envelope = _envelope(
            "task.created",
            payload={
                "title": row["title"],
                "description": row["description"],
                "acceptance_criteria": row["acceptance_criteria"],
                "status": row["status"] or "created",
                RECONSTRUCTED_KEY: True,
                "reconstructed_at": now,
            },
            trace={
                "project_id": row["project_id"],
                "work_order_id": row["work_order_id"],
                "task_id": row["task_id"],
            },
            when=row["created_at"] or now,
        )
        try:
            _write_to_dual_canonical(envelope, db_path)
            written["tasks"] += 1
        except Exception as exc:  # noqa: BLE001
            failures.append(f"task {row['task_id']}: {type(exc).__name__}: {exc}")

    conn = sqlite3.connect(str(db_path))
    try:
        after = _missing_counts(conn)
    finally:
        conn.close()

    result["written"] = written
    result["after"] = after
    # MEASURED, NOT ASSUMED. If the counts did not fall by what was written, the events
    # landed somewhere a replay will not find them, and saying so is the point.
    result["ok"] = not failures and after["work_orders"] == 0 and after["tasks"] == 0
    if failures:
        result["failures"] = failures[:20]
        result["failure_count"] = len(failures)
    return result
