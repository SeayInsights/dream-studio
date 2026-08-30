"""Close a mis-scoped work order at its true scope, and carry the rest somewhere honest.

Task 3 of WO-WO-LIFECYCLE-SURFACE, and it is deliberately narrow.

WHAT THIS IS NOT FOR. Operator ruling 2026-08-26: carry-over is not "I want to work on
something else". Tasks that belong to a work order stay on it, and you switch work orders
instead -- the ready set exists so that switching is possible without abandoning anything.

WHAT IT IS FOR: a genuine SCOPE change. The remaining tasks turned out to belong to
different work, or the work order was mis-scoped when it was authored. Today the only ways
to express that are ``--force`` (which pollutes the bypass audit with something that is not
a bypass) or cancelling the tasks (which is a lie -- the work still needs doing).

THE DANGER, NAMED BY THE CODE THIS SITS NEXT TO. ``verify_gaps`` refuses to spawn a sibling
work order for a gap in open work, because "spawning a sibling declares the reviewed work
order complete and re-homes its remainder -- routing AROUND the tasks_done gate that
already refuses to close a work order with open tasks." Carry-over is that exact shape. The
difference cannot be intent, which no gate can read, so it is these four properties:

  1. A recorded REASON, substantive enough to weigh later.
  2. Something must REMAIN. A work order that carries everything away was not re-scoped, it
     was abandoned -- and closing it would assert that work happened when none did.
  3. The split is recorded on BOTH work orders, so neither side is a dead end.
  4. tasks_done still runs. A carried task stops blocking ONLY because the split is
     recorded; delete a task with no record and the gate refuses exactly as before. That
     is what keeps this from becoming the bypass it resembles.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CARRY_KIND = "report"
CARRY_KEY = "carry_over"

_MIN_REASON = 20


def carried_task_ids(work_order_id: str, *, db_path: Path) -> set[str]:
    """Task ids this work order recorded as carried to another work order.

    The close gate consults this rather than the task's status. A task whose row says
    'deleted' with no carry record still blocks the close -- otherwise deleting tasks
    would become a way to close a work order with its work undone, which is the lie this
    whole mechanism exists to avoid.
    """
    from .artifacts import get_wo_artifact

    raw = get_wo_artifact(work_order_id, CARRY_KIND, instance_key=CARRY_KEY, db_path=db_path)
    if not raw:
        return set()
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return set()
    return {
        entry.get("from_task_id")
        for entry in payload.get("moved", [])
        if isinstance(entry, dict) and entry.get("from_task_id")
    }


def _open_tasks(conn: sqlite3.Connection, work_order_id: str) -> dict[str, sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return {
        row["task_id"]: row
        for row in conn.execute(
            "SELECT task_id, title, description, acceptance_criteria, status"
            " FROM business_tasks WHERE work_order_id = ?"
            "   AND status NOT IN ('complete', 'cancelled', 'deleted')",
            (work_order_id,),
        ).fetchall()
    }


def carry_over(
    *,
    work_order_id: str,
    task_ids: list[str],
    reason: str,
    title: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Move out-of-scope tasks to a new linked work order and record the split.

    Does NOT close the original -- close it afterwards, through the normal gates. Closing
    here would make carry-over a close path that skipped them, which is the thing being
    avoided.
    """
    from .artifacts import set_wo_artifact
    from .mutations import create_task, create_work_order
    from .start_shared import _require_db

    text = (reason or "").strip()
    if len(text) < _MIN_REASON:
        return {
            "ok": False,
            "error": (
                "A carry-over needs a reason a later reader can weigh: what changed about "
                "the scope, or how the work order was mis-scoped when authored. "
                "Carry-over is not for moving work you would rather do later — switch "
                "work orders instead (`ds work-order next`)."
            ),
        }
    if not task_ids:
        return {"ok": False, "error": "No tasks named to carry over."}

    db_path = _require_db(source_root, dream_studio_home)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        wo = conn.execute(
            "SELECT project_id, milestone_id, work_order_type, title"
            " FROM business_work_orders WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if wo is None:
            return {"ok": False, "error": f"Work order not found: {work_order_id}"}
        open_tasks = _open_tasks(conn, work_order_id)
        total = conn.execute(
            "SELECT COUNT(*) FROM business_tasks WHERE work_order_id = ?", (work_order_id,)
        ).fetchone()[0]
    finally:
        conn.close()

    unknown = [t for t in task_ids if t not in open_tasks]
    if unknown:
        return {
            "ok": False,
            "error": (
                f"Not open tasks on this work order: {', '.join(unknown)}. "
                f"A completed task cannot be carried — it already happened here."
            ),
        }

    # SOMETHING MUST REMAIN. A work order that carries everything away was not re-scoped,
    # it was abandoned, and closing it afterwards would assert work happened when none did.
    # Block it, and name the honest alternative rather than leaving the operator to find
    # --force.
    if len(task_ids) >= total:
        return {
            "ok": False,
            "error": (
                f"This would carry away all {total} task(s), leaving nothing to close at. "
                f"That is not a re-scope, it is an abandonment — and closing the original "
                f"afterwards would assert that work happened here when none did. "
                f"Re-title this work order instead, or block it with a reason "
                f"(`ds work-order block {work_order_id} --reason ...`)."
            ),
        }

    now = datetime.now(UTC).isoformat()
    created = create_work_order(
        project_id=wo["project_id"],
        milestone_id=wo["milestone_id"],
        title=title,
        description=(
            f"Carried out of work order {work_order_id} on {now[:10]} because the scope "
            f"changed.\n\nReason given: {text}\n\n"
            f"These tasks were authored on {wo['title']!r} and turned out to belong to "
            f"different work. The original was closed at its true scope; this work order "
            f"holds the remainder."
        ),
        work_order_type=wo["work_order_type"],
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not created.get("ok"):
        return created
    new_wo_id = created["work_order_id"]

    moved: list[dict[str, str]] = []
    for task_id in task_ids:
        row = open_tasks[task_id]
        made = create_task(
            work_order_id=new_wo_id,
            project_id=wo["project_id"],
            title=row["title"],
            description=row["description"] or "",
            acceptance_criteria=row["acceptance_criteria"],
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
        if not made.get("ok"):
            return {
                "ok": False,
                "error": f"Could not re-create task {task_id} on {new_wo_id}: {made}",
                "partial_work_order": new_wo_id,
            }
        moved.append(
            {
                "from_task_id": task_id,
                "to_task_id": made["task_id"],
                "title": row["title"],
            }
        )
        _emit_task_deleted(
            task_id=task_id,
            work_order_id=work_order_id,
            project_id=wo["project_id"],
            milestone_id=wo["milestone_id"],
            now=now,
            carried_to=new_wo_id,
        )

    record = json.dumps(
        {
            "reason": text,
            "carried_to": new_wo_id,
            "carried_from": work_order_id,
            "moved": moved,
            "recorded_at": now,
        },
        indent=2,
    )
    # BOTH SIDES. The original needs it because the close gate reads it; the new work
    # order needs it because a reader who lands there must be able to get back to where
    # the work came from, and a one-way link is how provenance is lost.
    set_wo_artifact(work_order_id, CARRY_KIND, record, instance_key=CARRY_KEY, db_path=db_path)
    set_wo_artifact(new_wo_id, CARRY_KIND, record, instance_key=CARRY_KEY, db_path=db_path)

    return {
        "ok": True,
        "work_order_id": work_order_id,
        "carried_to": new_wo_id,
        "moved": moved,
        "remaining_tasks": total - len(task_ids),
        "next_command": f"ds work-order close {work_order_id}",
    }


def _emit_task_deleted(
    *,
    task_id: str,
    work_order_id: str,
    project_id: str,
    milestone_id: str | None,
    now: str,
    carried_to: str,
) -> None:
    """Remove the task from THIS work order in the projection.

    business_tasks is a projection, so a direct UPDATE would be erased on the next
    rebuild. The event carries the destination in its payload, which makes the move
    reconstructible from the event stream alone rather than only from the artifact.
    """
    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        _spool_writer.write_event(
            CanonicalEventEnvelope(
                event_type="task.deleted",
                session_id=None,
                payload={
                    "deletion_context": "carried_to_another_work_order",
                    "carried_to": carried_to,
                },
                timestamp=now,
                severity="info",
                trace={
                    "domain": "sdlc",
                    "project_id": project_id,
                    "milestone_id": milestone_id,
                    "work_order_id": work_order_id,
                    "task_id": task_id,
                    "attribution_status": "fully_attributed",
                },
            ).to_dict()
        )
        from core.projections.runner import sync_tick as _sync_tick

        _sync_tick()
    except Exception:
        # The artifact is the gate's source of truth, so a failed emit degrades to a
        # stale-looking task row rather than a wrong close decision.
        pass
