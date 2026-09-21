"""Work-order lifecycle mutations: task-done, block, unblock."""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect
from core.work_orders.task_status import (
    TASK_ABANDONED_STATUSES,
    TASK_DONE_STATUSES,
    is_open,
    sql_placeholders,
    status_for,
)


def _require_db(source_root: Path, dream_studio_home: Path | None) -> Path:
    # Lazy import via ds.py — see core.projects.queries._require_db for rationale.
    from interfaces.cli.ds import resolve_installed_runtime_paths

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing. Run rehearsal-install first.")
    return paths.sqlite_path


def mark_task_done(
    *,
    work_order_id: str,
    task_id: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
    planning_root: Path | None = None,
) -> dict[str, Any]:
    db_path = _require_db(source_root, dream_studio_home)
    with _connect(db_path) as conn:
        task_row = conn.execute(
            "SELECT t.task_id, t.work_order_id, t.title, t.status, t.project_id,"
            " wo.milestone_id"
            " FROM business_tasks t"
            " LEFT JOIN business_work_orders wo ON t.work_order_id = wo.work_order_id"
            " WHERE t.task_id = ?",
            (task_id,),
        ).fetchone()
        if task_row is None:
            return {"ok": False, "error": f"Task not found: {task_id}"}

        t_id, t_wo_id, t_title, t_status, t_project_id, t_milestone_id = task_row
        if t_wo_id != work_order_id:
            return {
                "ok": False,
                "error": f"Task {task_id} does not belong to work order {work_order_id}",
            }

        now = datetime.now(UTC).isoformat()

        # The vocabulary comes from task_status, not from a literal spelled here. This site
        # previously excluded only the settled-and-cancelled pair by name, omitting the
        # third stored value -- 27 tasks use it -- so a finished task counted as still
        # remaining in the number that feeds the tasks_done close gate.
        _settled = TASK_DONE_STATUSES + TASK_ABANDONED_STATUSES
        remaining = conn.execute(
            "SELECT COUNT(*) FROM business_tasks"
            f" WHERE work_order_id = ? AND status NOT IN ({sql_placeholders(_settled)})",
            (work_order_id, *_settled),
        ).fetchone()[0]
        # Task is being completed via event but not yet written directly; subtract 1
        # unless the projection already applied a prior completion for this task.
        if is_open(t_status):
            remaining -= 1

        task_index = (
            conn.execute(
                "SELECT COUNT(*) FROM business_tasks"
                " WHERE work_order_id = ? AND created_at <= ("
                "   SELECT created_at FROM business_tasks WHERE task_id = ?"
                ")",
                (work_order_id, task_id),
            ).fetchone()[0]
            - 1
        )

    # WO-FILESDB-C2: the context checkbox is no longer mutated on disk. Task status
    # lives in business_tasks (the task.completed event below + its projection); the
    # context artifact is a start-time briefing and live status comes from
    # `ds work-order tasks <id>`, not a read-modify-write of context.md.

    event_write_error: str | None = None
    completed_event_id: str | None = None
    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        _envelope = CanonicalEventEnvelope(
            event_type="task.completed",
            session_id=None,
            payload={
                "task_id": task_id,
                "work_order_id": work_order_id,
                "tasks_remaining": remaining,
            },
            timestamp=now,
            severity="info",
            trace={
                "domain": "sdlc",
                "project_id": t_project_id,
                "milestone_id": t_milestone_id,
                "work_order_id": work_order_id,
                "task_id": task_id,
                "attribution_status": "fully_attributed",
            },
        ).to_dict()
        completed_event_id = _envelope.get("event_id")
        _spool_writer.write_event(_envelope)
    except Exception as _exc:
        event_write_error = f"{type(_exc).__name__}: {_exc}"[:200]

    # Materialize the task.completed event into the business_tasks read model now,
    # mirroring create_task/create_work_order. Without this, status stays 'pending'
    # in the read model (and `ds work-order tasks`) until an unrelated sync_tick()
    # runs — the WO-TASKDONE-SYNC defect.
    projection_error: str | None = None
    try:
        from core.projections.runner import sync_tick as _sync_tick

        _sync_tick()
    except Exception as _exc:
        projection_error = f"{type(_exc).__name__}: {_exc}"[:200]

    try:
        from core.sdlc.active_task import clear_active_task as _clear_active_task
        from core.sdlc.active_task import get_active_task as _get_active_task

        _active = _get_active_task()
        if _active is not None and _active.task_id == task_id:
            _clear_active_task()
    except Exception:
        pass

    # REPORT THE STATUS THE AUTHORITY HOLDS, not the one we asked for (issue #718).
    # Reporting only the two caught failures above would not have caught the defect that
    # motivated this work: event d441e451 reached business_canonical_events -- so
    # write_event succeeded -- and then failed a FOREIGN KEY constraint inside the
    # projection, where framework_engine_dispatch catches the handler error, dead-letters
    # it, and returns a ProjectionResult normally. NOTHING RAISED, and task c1698f88 has no
    # business_tasks row to this day while its caller was told "complete".
    #
    # Read-model lag is NOT the same failure as a lost write, and the two are separated
    # here deliberately. A projection that has simply not run yet (async deployment, or a
    # daemon owning the tick) will materialize this event on its next pass or on a rebuild,
    # because the event itself is durable -- that is pending, not failed. A projection that
    # queued this event for retry or dead-lettered it will NOT recover without
    # intervention. Only the second case is a false-done, so only it fails the call.
    observed_status: str | None = None
    read_back_error: str | None = None
    projection_stalled = False
    try:
        with _connect(db_path) as conn:
            _row = conn.execute(
                "SELECT status FROM business_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            observed_status = _row[0] if _row is not None else None
            if completed_event_id:
                projection_stalled = bool(
                    conn.execute(
                        "SELECT 1 FROM projection_dead_letter"
                        " WHERE event_id = ? AND status = 'active' LIMIT 1",
                        (completed_event_id,),
                    ).fetchone()
                    or conn.execute(
                        "SELECT 1 FROM projection_retry_queue WHERE event_id = ? LIMIT 1",
                        (completed_event_id,),
                    ).fetchone()
                )
    except Exception as _exc:
        # An older authority may predate these tables; never invent a verdict from a
        # failed read -- say the read failed and leave the judgement to the fields above.
        read_back_error = f"{type(_exc).__name__}: {_exc}"[:200]

    recorded = observed_status in TASK_DONE_STATUSES

    result: dict[str, Any] = {
        "ok": event_write_error is None and (recorded or not projection_stalled),
        "task_id": task_id,
        "work_order_id": work_order_id,
        "title": t_title,
        "status": observed_status or "unknown",
        "tasks_remaining": remaining,
        "task_index": task_index,
    }
    if event_write_error is not None:
        result["event_write_error"] = event_write_error
    if projection_error is not None:
        result["projection_error"] = projection_error
    if read_back_error is not None:
        result["read_back_error"] = read_back_error
    if not recorded and result["ok"]:
        result["read_model_pending"] = True
        result["note"] = (
            f"task.completed was recorded, but business_tasks still reports"
            f" {observed_status or 'no row'}. The read model will catch up on the next"
            " projection pass; `ds work-order tasks` reflects it only once it does."
        )
    if not result["ok"]:
        result["error"] = (
            f"Task {task_id} was NOT recorded as done: business_tasks reports"
            f" {observed_status or 'no row'}."
            + (
                " Its task.completed event is stuck in the projection --"
                " see `ds projection dead-letter list`."
                if projection_stalled
                else " The task.completed event could not be written."
            )
        )
    if result["ok"] and remaining == 0:
        result["all_tasks_complete"] = True
        result["suggested_action"] = (
            f"All tasks complete. Close work order: ds work-order close {work_order_id}"
        )
    # WO 80c0e61b: RECORD WHICH COMMITS THIS WORK ORDER OWNS, on EVERY task-done rather
    # than only the last. A delivery boundary is a time window, and two work orders worked
    # on in the same period have overlapping windows — measured, subtracting on them drops
    # commits that really do belong. Per-commit ownership is the only signal that separates
    # interleaved work, and it can only be captured while the work is happening.
    try:
        from core.work_orders.range_attribution import record_commit_ownership
        from core.work_orders.verify_executor import resolve_project_root

        _owned = record_commit_ownership(
            work_order_id,
            repo_root=resolve_project_root(work_order_id, db_path),
            db_path=db_path,
        )
        if _owned:
            result["commits_recorded"] = len(_owned)
    except Exception as _exc:  # noqa: BLE001 - finishing a task must not fail on bookkeeping
        result["commit_ownership_error"] = f"{type(_exc).__name__}: {_exc}"[:200]

    # WO-BOUNDARY-OPEN-END task 1, second half: pin the boundary when the LAST task is
    # done, not only at close.
    #
    # A work order is routinely verified BEFORE it is closed -- `ds work-order verify` is a
    # separate command an operator runs to decide whether to close at all. Without a stamp
    # here that verify still grades every commit since the work order started. Task 1 named
    # both halves; shipping only the close half was a false-done, caught by this work
    # order's own independent review.
    #
    # OUTSIDE the `with _connect(...)` block on purpose. The first attempt sat inside it,
    # so record_delivery_boundary_end opened a SECOND connection to the same SQLite file
    # while the outer transaction held it, the write failed, and a bare `except: pass`
    # swallowed it -- the stamp silently never happened. That is the ERROR HANDLING
    # HONESTY rule in this repo's own SDLC baseline, broken by the code enforcing it.
    #
    # Still best-effort, because finishing a task must not fail on bookkeeping -- but the
    # failure is REPORTED on the result now instead of vanishing.
    if result["ok"] and remaining == 0:
        try:
            from core.work_orders.delivery_boundary import record_delivery_boundary_end
            from core.work_orders.verify_executor import resolve_project_root

            _boundary = record_delivery_boundary_end(
                work_order_id,
                repo_root=resolve_project_root(work_order_id, db_path),
                db_path=db_path,
                now=now,
            )
            if _boundary.get("end_commit"):
                result["delivery_boundary_end"] = _boundary["end_commit"]
            elif _boundary.get("reason") or _boundary.get("end_record_error"):
                result["delivery_boundary_end_error"] = str(
                    _boundary.get("end_record_error") or _boundary.get("reason")
                )[:200]
        except Exception as exc:  # noqa: BLE001 - a task-done must not fail on bookkeeping
            result["delivery_boundary_end_error"] = f"{type(exc).__name__}: {exc}"[:200]

    return result


def block_work_order(
    *,
    work_order_id: str,
    reason: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    db_path = _require_db(source_root, dream_studio_home)
    with _connect(db_path) as conn:
        wo_row = conn.execute(
            "SELECT work_order_id, title, project_id FROM business_work_orders WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if wo_row is None:
            return {"ok": False, "error": f"Work order not found: {work_order_id}"}

        _, title, project_id = wo_row
        now = datetime.now(UTC).isoformat()

        conn.execute(
            "UPDATE business_work_orders"
            " SET status = ?, blocked_at = ?, block_reason = ?,"
            " updated_at = ?, last_updated_at = ?"
            " WHERE work_order_id = ?",
            (
                status_for("work_order.blocked", work_order=True),
                now,
                reason,
                now,
                now,
                work_order_id,
            ),
        )

        try:
            import spool.writer as _spool_writer

            from canonical.events.envelope import CanonicalEventEnvelope

            _spool_writer.write_event(
                CanonicalEventEnvelope(
                    event_type="work_order.blocked",
                    session_id=None,
                    payload={
                        "work_order_id": work_order_id,
                        "title": title,
                        "project_id": project_id,
                        "reason": reason,
                    },
                    timestamp=now,
                    severity="warning",
                    trace={
                        "domain": "sdlc",
                        "work_order_id": work_order_id,
                        "project_id": project_id,
                        "attribution_status": "fully_attributed",
                    },
                ).to_dict()
            )
        except Exception:
            pass

    return {
        "ok": True,
        "work_order_id": work_order_id,
        "status": "blocked",
        "block_reason": reason,
    }


def unblock_work_order(
    *,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    db_path = _require_db(source_root, dream_studio_home)
    with _connect(db_path) as conn:
        wo_row = conn.execute(
            "SELECT work_order_id, title, status, project_id FROM business_work_orders"
            " WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if wo_row is None:
            return {"ok": False, "error": f"Work order not found: {work_order_id}"}

        _, title, wo_status, project_id = wo_row
        if wo_status != "blocked":
            return {
                "ok": False,
                "error": f"Work order is not blocked (status: {wo_status})",
            }

        now = datetime.now(UTC).isoformat()

        conn.execute(
            "UPDATE business_work_orders"
            " SET status = ?, unblocked_at = ?, block_reason = NULL,"
            " updated_at = ?, last_updated_at = ?"
            " WHERE work_order_id = ?",
            (status_for("work_order.unblocked", work_order=True), now, now, now, work_order_id),
        )

    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        _spool_writer.write_event(
            CanonicalEventEnvelope(
                event_type="work_order.unblocked",
                session_id=None,
                payload={
                    "work_order_id": work_order_id,
                    "title": title,
                    "project_id": project_id,
                },
                timestamp=now,
                severity="info",
                trace={
                    "domain": "sdlc",
                    "work_order_id": work_order_id,
                    "project_id": project_id,
                    "attribution_status": "fully_attributed",
                },
            ).to_dict()
        )
    except Exception:
        pass

    return {
        "ok": True,
        "work_order_id": work_order_id,
        "status": "in_progress",
    }


def reopen_work_order(
    *,
    work_order_id: str,
    reason: str = "",
    source_root: Path | None = None,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Set a closed work order back to in_progress (designated business-state writer).

    Used by the outcome eval (core/eval/runner.py) when a closed WO's symptom
    regresses after close. Keeping this UPDATE in the work-order mutation layer —
    rather than writing business_work_orders from the eval layer — respects the
    authority boundary (dependency Rule 3: the work-order layer is the designated
    writer of business_* state). Emits ``work_order.reopened`` and syncs the read
    model, mirroring block/unblock.
    """
    db_path = _require_db(source_root or Path.cwd(), dream_studio_home)
    with _connect(db_path) as conn:
        wo_row = conn.execute(
            "SELECT work_order_id, title, status, project_id FROM business_work_orders"
            " WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if wo_row is None:
            return {"ok": False, "error": f"Work order not found: {work_order_id}"}

        _, title, prev_status, project_id = wo_row
        now = datetime.now(UTC).isoformat()

        conn.execute(
            "UPDATE business_work_orders"
            " SET status = ?, updated_at = ?, last_updated_at = ?"
            " WHERE work_order_id = ?",
            (status_for("work_order.reopened", work_order=True), now, now, work_order_id),
        )

    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        _spool_writer.write_event(
            CanonicalEventEnvelope(
                event_type="work_order.reopened",
                session_id=None,
                payload={
                    "work_order_id": work_order_id,
                    "title": title,
                    "project_id": project_id,
                    "previous_status": prev_status,
                    "reason": reason,
                },
                timestamp=now,
                severity="warning",
                trace={
                    "domain": "sdlc",
                    "work_order_id": work_order_id,
                    "project_id": project_id,
                    "attribution_status": "fully_attributed",
                },
            ).to_dict()
        )
    except Exception:
        pass

    try:
        from core.projections.runner import sync_tick as _sync_tick

        _sync_tick()
    except Exception:
        pass

    return {
        "ok": True,
        "work_order_id": work_order_id,
        "status": "in_progress",
        "previous_status": prev_status,
    }


#: A plain directory or file name with no separator -- ``docs``, ``schemas``, ``tests``.
#: Kept deliberately narrow so a fragment of prose swept into the clause cannot pass as a
#: path. Mirrored by ``runtime.lib.enforcement._is_boundary_path``; the two are held in step
#: by tests/unit/test_boundary_keeps_bare_directories.py, because a producer that emits what
#: the consumer discards is the exact failure this pair exists to prevent.
_BARE_PATH_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


def _is_boundary_path(part: str) -> bool:
    """Whether a comma-separated boundary entry names a path rather than prose."""
    if not part:
        return False
    return "/" in part or "." in part or bool(_BARE_PATH_NAME.match(part))


def compose_module_boundary(description: str, module_boundary: str | list[str] | None) -> str:
    """Put the boundary into the description in the exact form the parser reads.

    ``runtime.lib.enforcement.boundary_globs`` searches for a literal ``Module boundary:``
    clause and keeps the comma-separated parts that look like paths. Composing the clause
    here means the producer emits precisely what the consumer parses, instead of an author
    recalling a literal documented nowhere -- which is why 0 of 25 in-progress work orders
    on the live authority carried one, and why edit attribution had no choice but to guess.

    A BARE TOP-LEVEL DIRECTORY IS A PATH. The filter here used to require ``/`` or ``.``,
    so ``docs``, ``schemas``, ``config``, ``tests`` and ``dist`` were dropped on the way in,
    silently and with nothing said to the author. A work order declaring
    ``--module-boundary "core/gates, docs, tests"`` was stored owning only ``core/gates``;
    its own edits under ``docs/`` then matched no boundary it declared, so the stop hook
    attributed them to whichever OTHER in-progress work orders happened to spell a covering
    path, and demanded an authority write against work orders the session never touched.
    Observed on the live authority: a boundary of 15 declared paths stored as 12. That is
    precisely the "looks declared and matches nothing" failure the guard below names.

    Whitespace is not the discriminator either -- an absolute path on this operator's
    machine contains a space (``C:/Users/<given name>/.codex/config.toml``), and six such
    entries on a live work order would be lost by a no-spaces rule. The placeholder is
    spelled with angle brackets rather than a name, because two guards disagree about what
    a safe example looks like. The publication rule exempts a user segment beginning with
    the word Example OR with ``<``; the scrubbed-path test in
    test_install_bootstrap_sqlite_authority forbids that same Example-named home path
    outright. A path named after the example user satisfies the first and fails the second
    -- which is exactly how one got here, and how main's Full CI went red for three merges
    while every PR smoke stayed green, the publication suite being post-merge only. The
    bracketed form passes both guards and keeps the space the example exists to demonstrate.

    An already-present clause is left alone: a caller who wrote it by hand is not
    second-guessed, and re-composing would duplicate it.
    """
    if not module_boundary:
        return description
    if "Module boundary:" in (description or ""):
        return description
    parts = (
        [p.strip() for p in module_boundary.split(",")]
        if isinstance(module_boundary, str)
        else [str(p).strip() for p in module_boundary]
    )
    usable = [p for p in parts if _is_boundary_path(p)]
    if not usable:
        # Nothing the parser would keep. Silently storing an unparseable boundary would
        # look declared and match nothing -- the failure this function exists to end.
        return description
    clause = "Module boundary: " + ", ".join(usable) + "."
    body = (description or "").rstrip()
    if not body:
        return clause
    separator = chr(10) * 2
    return body + separator + clause


def _unverified_claim_note(description: str) -> str | None:
    """Asserted absences in a description that cite nothing, as one operator-facing line.

    Operator ruling 2026-08-28: "those gates need to be adjusted so that you have to look
    without assuming."

    Stamped at the moment a claim ENTERS the authority, because that is when it is cheap to
    settle. One work order in this session was registered claiming an unprojectable event
    "retries forever and blocks the queue"; the projection framework already dead-lettered
    after max retries, the live engine demonstrated it while the registration was being
    written, and the task had to be retitled "NO WORK NEEDED". A single command would have
    prevented it.

    ADVISORY BY DESIGN. It never blocks: a defect must always be registerable, and refusing
    a registration would trade a small error for a large one. It returns a note the caller
    surfaces, so an unchecked assertion is visible rather than indistinguishable from a
    verified one.
    """
    try:
        from core.gates.unverified_claims import audit_claims

        report = audit_claims(description or "")
        if report.passed:
            return None
        triggers = ", ".join(sorted({c.trigger.lower() for c in report.unverified}))
        return (
            f"{len(report.unverified)} asserted absence(s) cite nothing ({triggers}). "
            "These are claims about the existing system -- run the check and paste what it "
            "said, or the claim reads as fact and nothing downstream questions it."
        )
    except Exception:
        return None  # an advisory note must never break a registration


def create_work_order(
    *,
    project_id: str,
    milestone_id: str | None = None,
    title: str,
    description: str = "",
    work_order_type: str | None = None,
    originating_symptom: str | None = None,
    module_boundary: str | list[str] | None = None,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Emit a work_order.created event; WorkOrderProjection materializes the row.

    ``module_boundary`` is the paths this work order owns, and passing it is how edit
    attribution stops guessing. The boundary is read back by
    ``runtime.lib.enforcement.boundary_globs``, which searches the DESCRIPTION for a
    literal ``Module boundary:`` clause -- there is no column for it. Nothing required
    that clause and nothing composed it, so on the live authority 0 of 25 in-progress
    work orders carried one. With no boundary to match, attribution falls back to the
    most recently started work order, which in a project with one open work order stamps
    every edit in that repo with it regardless of subject. The operator's report:
    switching projects, editing one unrelated file, and being blocked by a stop hook
    demanding an authority write against someone else's research work order --
    repeatedly, until bypassing became routine.

    So the clause is COMPOSED HERE from an argument rather than remembered by an author.
    A rule enforced by a regex over prose that no door produces is not a rule; it is a
    hope. Passing a list or a comma-separated string both work; the stored form is the
    one the parser reads, asserted by a test that runs the real parser over the real
    composed description.

    Pure event emitter — no direct INSERT to business_work_orders. The
    WorkOrderProjection daemon (5-second poll or synchronous tick) materializes
    the row from the canonical event. Cross-session reads are unaffected; the
    daemon runs between scope and start sessions.

    Returns::

        {"ok": True, "work_order_id": str, "project_id": str,
         "milestone_id": str | None, "title": str, "status": "created"}

    or on missing project::

        {"ok": False, "error": "Project not found: <id>"}
    """

    if milestone_id is None:
        return {
            "ok": False,
            "error": "milestone_id is required: every work order must belong to a milestone",
        }

    db_path = _require_db(source_root, dream_studio_home)
    work_order_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT project_id FROM business_projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if row is None:
            return {"ok": False, "error": f"Project not found: {project_id}"}
        ms_row = conn.execute(
            "SELECT milestone_id FROM business_milestones WHERE milestone_id = ?",
            (milestone_id,),
        ).fetchone()
        if ms_row is None:
            return {"ok": False, "error": f"Milestone not found: {milestone_id}"}

    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        _payload: dict[str, Any] = {
            "title": title,
            "status": "created",
            "type": work_order_type or "",
        }
        if originating_symptom is not None:
            _payload["originating_symptom"] = originating_symptom
        # Carry the description, with the module boundary composed into it. Neither the
        # payload nor the projection handled description before, so the field the CLI
        # advertises was accepted and silently dropped -- and the boundary that lives
        # inside it could never be declared, which is why attribution had to guess.
        _payload["description"] = compose_module_boundary(description, module_boundary)
        _spool_writer.write_event(
            CanonicalEventEnvelope(
                event_type="work_order.created",
                session_id=None,
                payload=_payload,
                timestamp=now,
                severity="info",
                trace={
                    "domain": "sdlc",
                    "project_id": project_id,
                    "milestone_id": milestone_id,
                    "work_order_id": work_order_id,
                    "attribution_status": "fully_attributed",
                },
            ).to_dict()
        )
    except Exception:
        pass

    try:
        from core.projections.runner import sync_tick as _sync_tick

        _sync_tick()
    except Exception:
        pass

    _claim_note = _unverified_claim_note(description)
    return {
        "ok": True,
        "work_order_id": work_order_id,
        "project_id": project_id,
        "milestone_id": milestone_id,
        "title": title,
        "status": "created",
        **({"unverified_claims": _claim_note} if _claim_note else {}),
    }


def create_task(
    *,
    work_order_id: str,
    project_id: str,
    title: str,
    description: str = "",
    acceptance_criteria: str | None = None,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Insert a new task row with status 'pending'.

    Returns::

        {"ok": True, "task_id": str, "work_order_id": str,
         "title": str, "status": "pending"}

    or on missing work order::

        {"ok": False, "error": "Work order not found: <id>"}
    """

    db_path = _require_db(source_root, dream_studio_home)
    task_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    milestone_id: str | None = None
    with _connect(db_path) as conn:
        wo_row = conn.execute(
            "SELECT work_order_id, milestone_id FROM business_work_orders WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if wo_row is not None:
            milestone_id = wo_row[1]
        # If wo_row is None the work order was just emitted as an event but not yet
        # materialized by the ProjectionRunner. Proceed with milestone_id=None — it
        # enriches the trace only and does not affect task creation correctness.

    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        _spool_writer.write_event(
            CanonicalEventEnvelope(
                event_type="task.created",
                session_id=None,
                payload={
                    "title": title,
                    "description": description,
                    "acceptance_criteria": acceptance_criteria,
                    "status": "created",
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
    except Exception:
        pass

    try:
        from core.projections.runner import sync_tick as _sync_tick

        _sync_tick()
    except Exception:
        pass

    _claim_note = _unverified_claim_note(description)
    result: dict[str, Any] = {
        "ok": True,
        "task_id": task_id,
        "work_order_id": work_order_id,
        "title": title,
        "status": "pending",
        **({"unverified_claims": _claim_note} if _claim_note else {}),
    }
    if acceptance_criteria is not None:
        result["acceptance_criteria"] = acceptance_criteria
    return result


def set_originating_symptom(
    *,
    work_order_id: str,
    symptom: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Set or update the originating_symptom on an existing work order.

    Direct UPDATE — used for post-creation backfills and defect WOs registered
    before the symptom was known. Emits no spool event (the field is metadata,
    not a lifecycle transition).

    Returns ``{"ok": True, "work_order_id": str}`` or ``{"ok": False, "error": ...}``.
    """
    db_path = _require_db(source_root, dream_studio_home)
    now = datetime.now(UTC).isoformat()
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT work_order_id FROM business_work_orders WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if row is None:
            return {"ok": False, "error": f"Work order not found: {work_order_id}"}
        conn.execute(
            "UPDATE business_work_orders SET originating_symptom = ?, updated_at = ?"
            " WHERE work_order_id = ?",
            (symptom, now, work_order_id),
        )
    return {"ok": True, "work_order_id": work_order_id}


def _settings_path_for_todowrite(source_root: Path) -> Path:
    return source_root / ".claude" / "settings.json"


def todowrite_should_emit(source_root: Path) -> bool:
    """Whether to emit a TodoWrite update payload (only inside Claude Code)."""

    return (
        bool(os.environ.get("CLAUDE_CODE")) or _settings_path_for_todowrite(source_root).is_file()
    )
