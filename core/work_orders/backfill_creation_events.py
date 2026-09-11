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

#: The status a row ACTUALLY comes back with after replaying only a creation event.
#:
#: Both created handlers hardcode it -- `work_order_projection` writes "created",
#: `task_projection` writes "pending" -- and NEITHER reads `payload["status"]`, nor
#: patches status in its follow-up COALESCE. So the status this module writes into the
#: payload is dead: write-only, never consumed.
#:
#: That makes a naive backfill WORSE THAN THE DEFECT IT REPAIRS. Measured on the live
#: authority: 465 of 493 event-less work orders (94.3%) and 1418 of 1706 event-less tasks
#: (83.1%) carry some other status -- 396 closed work orders, 1095 complete tasks. Filling
#: the gap with creation events alone would turn "a rebuild deletes the row" into "a
#: rebuild silently reopens 396 closed work orders and un-completes 1095 tasks", which is
#: the worse failure because the row is present and looks fine while lying about its state.
#: Found by an independent reviewer, by execution, before this was ever applied.
#:
#: Listed here rather than parsed out of the handlers, because a literal inside a dict
#: literal is not worth parsing -- but it is PINNED BY A TEST that drives a real rebuild
#: and reads the status back, so if a handler ever starts honouring the payload, the test
#: fails and this constant gets corrected rather than silently going stale.
_STATUS_AFTER_REPLAY = {"work_orders": "created", "tasks": "pending"}

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


def _same_status(value: str | None, default: str) -> bool:
    """Is this the replay default, ignoring case and surrounding whitespace?"""
    return (value or "").strip().casefold() == default.casefold()


def _status_at_risk(conn: sqlite3.Connection) -> dict[str, Any]:
    """Rows whose CURRENT status a creation-event replay would not reproduce.

    Reported whether or not the repair runs, because the count is the whole argument for
    not running it: a repair that restores the row and destroys its status is not a
    repair. `NULL` counts as the replay default, since that is what the row would get
    anyway.
    """
    out: dict[str, Any] = {}
    for kind, table, default in (
        ("work_orders", "business_work_orders", _STATUS_AFTER_REPLAY["work_orders"]),
        ("tasks", "business_tasks", _STATUS_AFTER_REPLAY["tasks"]),
    ):
        source = _WORK_ORDER_SQL if kind == "work_orders" else _TASK_SQL
        rows = conn.execute(
            f"SELECT COALESCE(status, ?) AS s, COUNT(*) FROM ({source})"
            " GROUP BY s ORDER BY COUNT(*) DESC",
            (default,),
        ).fetchall()
        by_status = {row[0]: row[1] for row in rows}
        # CASE AND PADDING ARE NOT A DIFFERENT STATE. An exact match treated 'Created'
        # and ' created ' as at-risk and refused the whole run over a cosmetic variant --
        # the safe direction, but a refusal nobody can act on is how a guard gets
        # switched off. Comparison is normalised; the report still shows the raw value,
        # because "your data says 'Created'" is itself worth seeing.
        out[kind] = {
            "would_survive": sum(n for s, n in by_status.items() if _same_status(s, default)),
            "would_be_overwritten": sum(
                n for s, n in by_status.items() if not _same_status(s, default)
            ),
            "replays_as": default,
            "by_status": by_status,
        }
    return out


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


def backfill(
    *, db_path: Path, apply: bool = False, allow_status_loss: bool = False
) -> dict[str, Any]:
    """Report -- and with `apply`, repair -- rows that carry no creation event.

    Returns the counts before and after, because a repair that does not say how much it
    repaired is indistinguishable from one that did nothing. Idempotent: rows that
    already have a creation event are never selected, so a second run is a no-op.

    REFUSES TO RUN while any row's status would not survive the replay it is creating.
    `allow_status_loss` exists so the refusal can be overridden deliberately and in
    writing, not so it can be cleared by habit -- it is not a flag to reach for, and the
    refusal names the exact counts rather than telling the caller to go and look.
    """
    now = datetime.now(UTC).isoformat()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        totals = _totals(conn)
        before = _missing_counts(conn)
        at_risk = _status_at_risk(conn)
        work_orders = [dict(r) for r in conn.execute(_WORK_ORDER_SQL)]
        tasks = [dict(r) for r in conn.execute(_TASK_SQL)]
    finally:
        conn.close()

    endangered = sum(at_risk[kind]["would_be_overwritten"] for kind in at_risk)
    result: dict[str, Any] = {
        "ok": True,
        "applied": apply,
        "totals": totals,
        "before": before,
        "status_at_risk": at_risk,
        "would_write": {"work_orders": len(work_orders), "tasks": len(tasks)},
    }

    # A DRY RUN THAT REPORTS RISK HAS NOT FAILED. `ok` answers "did what I asked
    # succeed", and what a dry run was asked to do is look. Collapsing the two made
    # `ok=False` the normal outcome of an inspection, which trains a caller to ignore it
    # -- and the first CLI wrapper would have rendered a routine look as a crash.
    result["would_refuse"] = bool(endangered) and not allow_status_loss

    if endangered and not allow_status_loss and apply:
        # THE REFUSAL IS THE FEATURE. Restoring a row while silently resetting its status
        # trades a visible loss for an invisible lie, and this tool exists for disaster
        # recovery, where a row that reads 'created' when it was closed is worse than a
        # row that is missing.
        result["ok"] = False
        result["applied"] = False
        result["after"] = before
        result["error"] = (
            f"Refused — {endangered} row(s) carry a status a creation-event replay cannot"
            f" reproduce: {at_risk['work_orders']['would_be_overwritten']} work order(s)"
            f" would come back as '{_STATUS_AFTER_REPLAY['work_orders']}' and"
            f" {at_risk['tasks']['would_be_overwritten']} task(s) as"
            f" '{_STATUS_AFTER_REPLAY['tasks']}'. Neither created handler reads"
            " payload['status'], so the status written here is never consumed. Emit the"
            " terminal lifecycle event per row (closed / blocked / started / deleted) so a"
            " replay reaches the true state, or pass allow_status_loss to accept it."
        )
        return result

    if not apply:
        result["after"] = before
        if result["would_refuse"]:
            result["note"] = (
                "Dry run — nothing was written, and --apply would be REFUSED:"
                f" {endangered} row(s) carry a status a creation-event replay cannot"
                f" reproduce ({at_risk['work_orders']['would_be_overwritten']} work"
                f" order(s), {at_risk['tasks']['would_be_overwritten']} task(s)). Looking"
                " succeeded; the repair is what is blocked."
            )
        else:
            result["note"] = (
                "Dry run — nothing was written. Re-run with --apply to emit these events."
            )
        return result

    # THE PUBLIC PATH, BECAUSE THE INGESTOR OWNS CANONICAL WRITES. An independent review
    # found this module importing `spool.ingestor._write_to_dual_canonical` -- a private
    # function -- and driving canonical-event writes itself, crossing the write boundary
    # from outside the ingestor while its own sibling `verify_gaps._emit_creation` used
    # the public writer in the same change. Events are written to the spool and the
    # INGESTOR moves them, which is the rule this repo already states.
    import spool.writer as _spool_writer
    from spool.ingestor import ingest as _ingest

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
            _spool_writer.write_event(envelope)
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
            _spool_writer.write_event(envelope)
            written["tasks"] += 1
        except Exception as exc:  # noqa: BLE001
            failures.append(f"task {row['task_id']}: {type(exc).__name__}: {exc}")

    # Drain the spool before measuring: the events are written, and until the ingestor
    # moves them the `after` counts would describe a repair that has not landed yet.
    try:
        _ingest(db_path=db_path)
    except Exception as exc:  # noqa: BLE001 - a failed drain is reported, not swallowed
        failures.append(f"ingest after emission: {type(exc).__name__}: {exc}")

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
