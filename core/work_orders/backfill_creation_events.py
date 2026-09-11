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

from .task_status import (
    TASK_STATUS_EVENT,
    WORK_ORDER_STATUS_EVENT,
    canonical_status,
)

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


#: Rows that DO have a creation event but whose status a replay would not reach, because
#: no terminal lifecycle event was ever emitted for them.
#:
#: MEASURED 2026-09-11 and larger than the population this module was built for: 342 work
#: orders and 1283 tasks. They survive a rebuild and come back WRONG -- 307 closed work
#: orders reopening, 1171 complete tasks un-completing -- which is the failure that reads
#: as success. The missing-creation-event population (493 + 1706) is deleted outright and
#: was the only thing counted until an independent review asked for the overlap.
_WO_NEEDS_TERMINAL = """
SELECT work_order_id, project_id, milestone_id, title, description, work_order_type,
       status, created_at, originating_symptom
FROM business_work_orders t
WHERE EXISTS (
    SELECT 1 FROM business_canonical_events e
    WHERE e.event_type = 'work_order.created' AND e.work_order_id = t.work_order_id
)
"""

_TASK_NEEDS_TERMINAL = """
SELECT task_id, work_order_id, project_id, title, description, status, created_at,
       acceptance_criteria
FROM business_tasks t
WHERE EXISTS (
    SELECT 1 FROM business_canonical_events e
    WHERE e.event_type = 'task.created' AND e.task_id = t.task_id
)
"""


def _needs_terminal(conn: sqlite3.Connection) -> tuple[list[dict], list[dict]]:
    """Rows with a creation event whose terminal event was never emitted."""
    wos, tasks = [], []
    for row in conn.execute(_WO_NEEDS_TERMINAL):
        row = dict(row)
        event = WORK_ORDER_STATUS_EVENT.get(canonical_status(row["status"], work_order=True))
        if not event:
            continue
        seen = conn.execute(
            "SELECT 1 FROM business_canonical_events WHERE event_type = ?"
            " AND work_order_id = ? LIMIT 1",
            (event, row["work_order_id"]),
        ).fetchone()
        if not seen:
            row["_terminal"] = event
            wos.append(row)
    for row in conn.execute(_TASK_NEEDS_TERMINAL):
        row = dict(row)
        event = TASK_STATUS_EVENT.get(canonical_status(row["status"]))
        if not event:
            continue
        seen = conn.execute(
            "SELECT 1 FROM business_canonical_events WHERE event_type = ? AND task_id = ?"
            " LIMIT 1",
            (event, row["task_id"]),
        ).fetchone()
        if not seen:
            row["_terminal"] = event
            tasks.append(row)
    return wos, tasks


def _missing_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """How many rows of each kind no replay could rebuild."""
    return {
        "work_orders": conn.execute(f"SELECT COUNT(*) FROM ({_WORK_ORDER_SQL})").fetchone()[0],
        "tasks": conn.execute(f"SELECT COUNT(*) FROM ({_TASK_SQL})").fetchone()[0],
    }


def _status_at_risk(conn: sqlite3.Connection) -> dict[str, Any]:
    """Rows whose status a replay still could not reproduce.

    THIS USED TO BE EVERY ROW NOT AT THE CREATION DEFAULT -- 465 work orders and 1418
    tasks -- because the backfill emitted a creation event and nothing else, so a replay
    landed on the handler's hardcoded status and a repair would have reopened 396 closed
    work orders. The repair now emits the TERMINAL lifecycle event too, so a status is
    reproduced rather than reset, and the question changes: not "is this row at the
    default" but "is there an event that produces this status at all".

    Answered from the declared vocabulary, so a status added there without an event that
    reaches it is reported here rather than discovered by someone running the repair.
    """
    out: dict[str, Any] = {}
    for kind, source, is_wo, table in (
        ("work_orders", _WORK_ORDER_SQL, True, WORK_ORDER_STATUS_EVENT),
        ("tasks", _TASK_SQL, False, TASK_STATUS_EVENT),
    ):
        rows = conn.execute(
            f"SELECT status, COUNT(*) FROM ({source}) GROUP BY status ORDER BY COUNT(*) DESC"
        ).fetchall()
        by_status = {row[0]: row[1] for row in rows}
        unreachable = {
            status: n
            for status, n in by_status.items()
            if canonical_status(status, work_order=is_wo) not in table
        }
        out[kind] = {
            "reproducible": sum(n for s, n in by_status.items() if s not in unreachable),
            "would_be_overwritten": sum(unreachable.values()),
            "unreachable_statuses": sorted(unreachable),
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


def _terminal_payload(event: str, row: dict, reason: str) -> dict[str, Any]:
    """The payload each terminal event's contract actually requires.

    READ FROM THE REGISTRY, NOT GUESSED. A first cut sent one shape to every terminal
    event and two failed on emission: `work_order.started` requires `type` and
    `work_order.blocked` requires `reason`, neither of which a closed-shaped payload
    carries. The failure was visible only because the repair reports per-row failures
    instead of swallowing them.
    """
    payload: dict[str, Any] = {
        "work_order_id": row["work_order_id"],
        "project_id": row["project_id"],
        "title": row["title"],
        RECONSTRUCTED_KEY: True,
    }
    if event == "work_order.started":
        payload["type"] = row["work_order_type"] or ""
    elif event == "work_order.blocked":
        # The row records no historical reason; saying it was reconstructed is truer
        # than inventing one.
        payload["reason"] = reason
    elif event == "work_order.closed":
        payload["forced"] = False
    return payload


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
        # And the rows that DO have a creation event and still replay to the wrong
        # status, which is the larger population and was never counted.
        stale_wos, stale_tasks = _needs_terminal(conn)
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
        "would_correct": {"work_orders": len(stale_wos), "tasks": len(stale_tasks)},
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
            f"Refused — {endangered} row(s) hold a status no event type can produce, so a"
            " replay cannot reproduce them even with the terminal lifecycle event this"
            " repair emits: "
            f"{at_risk['work_orders']['unreachable_statuses']} on work orders,"
            f" {at_risk['tasks']['unreachable_statuses']} on tasks. Add the event type and"
            " its handler, or pass allow_status_loss to accept the loss."
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

    written = {"work_orders": 0, "tasks": 0}
    failures: list[str] = []

    for row in work_orders:
        payload = {
            "title": row["title"],
            # The contract demands this key and no consumer reads it. `work_order.created`
            # declares `status` in payload_required_keys, so omitting it fails
            # emission -- but neither created handler reads it. Deleting it here was
            # tried and broke every emission; deleting it from the contract is a
            # cross-producer change, registered as WO b52d7f4c rather than done
            # quietly inside a backfill.
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
            continue
        # AND THE EVENT THAT LANDS IT ON ITS REAL STATUS. A creation event alone replays
        # to the handler's hardcoded default, which is why this refused to run at all
        # while 465 work orders sat at something else. The terminal event is read from
        # the declared vocabulary rather than a map kept here, so a status added there
        # without an event that produces it is a failure at the declaration.
        terminal = WORK_ORDER_STATUS_EVENT[canonical_status(row["status"], work_order=True)]
        if terminal:
            try:
                _spool_writer.write_event(
                    _envelope(
                        terminal,
                        payload=_terminal_payload(
                            terminal,
                            row,
                            "reconstructed from the row; the original reason was not recorded",
                        ),
                        trace={
                            "project_id": row["project_id"],
                            "milestone_id": row["milestone_id"],
                            "work_order_id": row["work_order_id"],
                        },
                        when=row["created_at"] or now,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                failures.append(
                    f"work_order {row['work_order_id']} terminal {terminal}:"
                    f" {type(exc).__name__}: {exc}"
                )

    for row in tasks:
        envelope = _envelope(
            "task.created",
            payload={
                "title": row["title"],
                "description": row["description"],
                "status": row["status"] or "created",
                "acceptance_criteria": row["acceptance_criteria"],
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
            continue
        terminal = TASK_STATUS_EVENT[canonical_status(row["status"])]
        if terminal:
            try:
                _spool_writer.write_event(
                    _envelope(
                        terminal,
                        payload={RECONSTRUCTED_KEY: True},
                        trace={
                            "project_id": row["project_id"],
                            "work_order_id": row["work_order_id"],
                            "task_id": row["task_id"],
                        },
                        when=row["created_at"] or now,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                failures.append(
                    f"task {row['task_id']} terminal {terminal}: {type(exc).__name__}: {exc}"
                )

    # THE DRAIN IS NOT THIS MODULE'S JOB. An independent review found a work-order module
    # invoking the spool ingestor, which is the same boundary crossing as calling its
    # private writer -- one level up. Events are written; ingestion moves them; the
    # `after` counts below therefore describe the authority as it stands, and only fall
    # once the ingestor runs.
    conn = sqlite3.connect(str(db_path))
    try:
        after = _missing_counts(conn)
    finally:
        conn.close()

    # THE ROWS THAT SURVIVE AND COME BACK WRONG. They need no creation event -- they have
    # one -- only the terminal event that lands them on their real status.
    corrected = {"work_orders": 0, "tasks": 0}
    for row in stale_wos:
        try:
            _spool_writer.write_event(
                _envelope(
                    row["_terminal"],
                    payload=_terminal_payload(
                        row["_terminal"],
                        row,
                        "reconstructed from the row; the original reason was not recorded",
                    ),
                    trace={
                        "project_id": row["project_id"],
                        "milestone_id": row["milestone_id"],
                        "work_order_id": row["work_order_id"],
                    },
                    when=row["created_at"] or now,
                )
            )
            corrected["work_orders"] += 1
        except Exception as exc:  # noqa: BLE001
            failures.append(f"work_order {row['work_order_id']} terminal: {exc}")
    for row in stale_tasks:
        try:
            _spool_writer.write_event(
                _envelope(
                    row["_terminal"],
                    payload={RECONSTRUCTED_KEY: True},
                    trace={
                        "project_id": row["project_id"],
                        "work_order_id": row["work_order_id"],
                        "task_id": row["task_id"],
                    },
                    when=row["created_at"] or now,
                )
            )
            corrected["tasks"] += 1
        except Exception as exc:  # noqa: BLE001
            failures.append(f"task {row['task_id']} terminal: {exc}")

    result["corrected"] = corrected
    result["written"] = written
    result["after"] = after
    # `ok` ANSWERS WHAT THIS MODULE CONTROLS: did every row it selected get its events
    # written. It used to also require the `after` counts to reach zero, which was true
    # only while this module drained the spool itself -- the boundary crossing a review
    # rejected. Ingestion is the ingestor's job, so the counts fall when it runs, and
    # `pending_ingestion` says so rather than reporting a successful repair as a failure.
    result["ok"] = (
        not failures
        and written["work_orders"] == len(work_orders)
        and written["tasks"] == len(tasks)
    )
    result["pending_ingestion"] = {
        "work_orders": after["work_orders"],
        "tasks": after["tasks"],
        "note": (
            "events are written to the spool; these counts fall once the ingestor moves"
            " them into business_canonical_events"
        ),
    }
    if failures:
        result["failures"] = failures[:20]
        result["failure_count"] = len(failures)
    return result
