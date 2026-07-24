"""Work-order close: gate preview and the close-work-order composer.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/close.py``. Holds
``check_close_gates`` (pure gate-evaluation preview) and ``close_work_order``
(the composer that re-runs gate evaluation inside the mutating connection,
mutates status, emits spool events, and computes the next-step hint). The
two structural extractions (``_check_tasks_done`` in ``close_gates.py``,
``_apply_report_only_continuation`` in ``close_continuation.py``) are called
here where their inline bodies used to sit. No other logic changes —
extracted verbatim from the original module.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect

from .close_continuation import _apply_report_only_continuation
from .close_gates import (
    _check_originating_symptom,
    _check_tasks_done,
    _evaluate_gates,
    _run_ac_gate,
)
from .close_shared import _lookup_work_order_and_gates, _require_db
from .models import TERMINAL_WO_STATUSES, terminal_wo_status_placeholders


def check_close_gates(
    *,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
    planning_root: Path | None = None,
) -> dict[str, Any]:
    """Preview gate evaluation for a work-order close. Does not mutate.

    Returns a dict shaped like:

        {
            "ok": True | False,
            "error": str (when ok=False, e.g. WO not found),
            # When ok=True:
            "work_order_id": str,
            "title": str,
            "wo_status": str,
            "type_id": str | None,
            "project_id": str,
            "milestone_id": str | None,
            "pre_gate": str | None,
            "post_gate": str | None,
            "gates_pass": bool,
            "gate_failures": list[str],
        }
    """

    p_root = planning_root or Path.cwd() / ".planning"
    db_path = _require_db(source_root, dream_studio_home)
    with _connect(db_path) as conn:
        meta = _lookup_work_order_and_gates(conn, work_order_id)
        if not meta.get("ok"):
            return meta

        failures = _evaluate_gates(
            conn,
            pre_gate=meta["pre_gate"],
            post_gate=meta["post_gate"],
            work_order_id=work_order_id,
            project_id=meta["project_id"],
            planning_root=p_root,
            db_path=db_path,
        )

        # Always-on AC gate preview.
        failures.extend(_run_ac_gate(conn, work_order_id=work_order_id, db_path=db_path))

    meta["gate_failures"] = failures
    meta["gates_pass"] = not failures
    return meta


def close_work_order(
    *,
    work_order_id: str,
    force: bool = False,
    source_root: Path,
    dream_studio_home: Path | None = None,
    planning_root: Path | None = None,
) -> dict[str, Any]:
    """Close a work order: evaluate gates, mutate status, emit spool events.

    On gate failure without ``force=True``, returns:

        {"ok": False, "error": "Gate check failed", "failures": [...]}

    On unknown WO:

        {"ok": False, "error": "Work order not found: <id>"}

    On success:

        {
            "ok": True,
            "work_order_id": str,
            "title": str,
            "status": "closed",
            "forced": bool,
            "bypassed_gates": list[str],   # populated when force=True
            "verify_warning": str | absent,  # inline verify was unreviewable (no commits)
            "next_work_order": {...} | absent,
            "next_command": str | absent,
            "milestone_complete": True | absent,
            "milestone_id": str | absent,
        }
    """

    p_root = planning_root or Path.cwd() / ".planning"
    db_path = _require_db(source_root, dream_studio_home)

    # T1: Auto-verify — if the independent_review gate applies and no verdict file
    # exists yet, run verify inline before the gate evaluation so operators don't
    # need to call `ds work-order verify` separately.
    _verify_result: dict[str, Any] | None = None
    _verify_ran = False

    with _connect(db_path) as _pre_conn:
        _pre_meta = _lookup_work_order_and_gates(_pre_conn, work_order_id)
    if not _pre_meta.get("ok"):
        return _pre_meta

    _post_gate_str = _pre_meta.get("post_gate") or ""
    if "independent_review" in [g.strip() for g in _post_gate_str.split("|") if g.strip()]:
        # WO-FILESDB-C2: a verdict may live in the authority (DB) or on the .planning
        # disk fallback — check both before triggering an inline re-verify.
        from core.work_orders.artifacts import has_wo_artifact as _has_verdict

        _verdict_path = p_root / "work-orders" / work_order_id / "review-verdict.json"
        _verdict_exists = (
            _has_verdict(work_order_id, "review_verdict", db_path=db_path)
            or _verdict_path.is_file()
        )
        if not _verdict_exists:
            # Deferred import: verify.py is a sibling module; deferring keeps the
            # import tree symmetrical with the other lazy imports in this module
            # and avoids any future circular-import risk if verify gains a close
            # dependency (e.g. for gap WO registration callbacks).
            from core.work_orders.verify import verify_work_order as _verify_wo

            try:
                _verify_result = _verify_wo(
                    work_order_id=work_order_id,
                    source_root=source_root,
                    dream_studio_home=dream_studio_home,
                    planning_root=p_root,
                )
            except Exception as exc:
                return {
                    "ok": False,
                    "error": f"Auto-verify raised an exception: {exc}",
                }
            _verify_ran = True
            if not _verify_result.get("ok"):
                return {
                    "ok": False,
                    "error": f"Auto-verify failed: {_verify_result.get('error', 'unknown error')}",
                }

    # Gaps exist when verify ran and returned passed=False with spawned remediation WOs.
    _has_gaps = (
        _verify_ran
        and _verify_result is not None
        and not _verify_result.get("passed")
        and bool(_verify_result.get("spawned_work_orders"))
    )
    _project_id_for_autostart = _pre_meta.get("project_id")

    # T2: Flush any pending task.completed events into the read model BEFORE we read
    # task statuses for the tasks_done gate below. mark_task_done already ticks inline
    # (WO-TASKDONE-SYNC), but an externally-marked task — or a crash between the spool
    # emit and the inline tick — could leave business_tasks behind. sync_tick never
    # raises, so a transient projection failure degrades to the daemon's next cycle.
    try:
        from core.projections.runner import sync_tick as _sync_tick

        _sync_tick()
    except Exception:
        pass

    with _connect(db_path) as conn:
        meta = _lookup_work_order_and_gates(conn, work_order_id)
        if not meta.get("ok"):
            return meta

        project_id = meta["project_id"]
        wo_milestone_id = meta["milestone_id"]
        title = meta["title"]

        gate_failures = _evaluate_gates(
            conn,
            pre_gate=meta["pre_gate"],
            post_gate=meta["post_gate"],
            work_order_id=work_order_id,
            project_id=project_id,
            planning_root=p_root,
            db_path=db_path,
        )

        # Always-on AC gate: run all executable checks across every task.
        # Runs regardless of WO type; additional to (not replacing) the existing gates.
        ac_failures = _run_ac_gate(conn, work_order_id=work_order_id, db_path=db_path)
        gate_failures.extend(ac_failures)

        # Re-run the originating symptom SQL-CHECK (if captured at registration).
        # A still-failing symptom means the fix never landed — block close unless forced.
        _orig_symptom = meta.get("originating_symptom")
        if _orig_symptom:
            _sym_failure = _check_originating_symptom(_orig_symptom, db_path)
            if _sym_failure:
                gate_failures.append(_sym_failure)

        # WO-LIVE-DATA-GATE T3: Dashboard truth gate — runs for telemetry/dashboard WO
        # types only.  A fresh/empty authority always vacuously passes, so this gate
        # does not affect unrelated PRs.  Non-telemetry/dashboard types are not gated.
        #
        # No 'dashboard' or 'telemetry' type_ids exist in business_work_order_types as
        # of this migration set; we gate on the explicit set below and document the
        # intent so that future type additions are opt-in.
        _DASHBOARD_TRUTH_GATED_TYPES: set[str] = {
            "dashboard",
            "telemetry",
            "data_pipeline",
            "saas_feature",
        }
        _wo_type_id = meta.get("type_id") or ""
        if _wo_type_id in _DASHBOARD_TRUTH_GATED_TYPES:
            from core.gates.dashboard_truth import run_dashboard_truth as _run_dt

            _dt_result = _run_dt(db_path)
            if not _dt_result["ok"]:
                _dt_details = "; ".join(
                    r["name"] + (f": {r['error']}" if r["error"] else "")
                    for r in _dt_result["results"]
                    if not r["passed"]
                )
                gate_failures.append(
                    f"dashboard_truth: live-authority invariants failed — {_dt_details}"
                )

        # T1: Task-completeness gate — NOTHING LEFT HANGING. See _check_tasks_done
        # for the full rationale (extracted verbatim; called here where the inline
        # block used to sit). This failure is NOT subject to the independent_review
        # bypass below — it always blocks unless forced, and a forced close records
        # it via the gate.bypassed path.
        gate_failures.extend(_check_tasks_done(conn, work_order_id))

        # WO-ESCALATION-LADDER T3: an escalated WO (reopened because the deterministic
        # verifier said NOT FIXED) must re-close through a PASSING independent review.
        # For escalated WOs the independent_review gate is mandatory: the gaps/unreviewable
        # bypasses below do NOT apply, and force cannot silently skip it (handled at the
        # force check). Non-escalated WOs keep their existing bypass semantics.
        from core.work_orders.escalation import read_escalation as _read_escalation

        _esc_row = _read_escalation(work_order_id, db_path=db_path)
        _is_escalated = bool(_esc_row and (_esc_row.get("escalation_level") or 0) >= 1)

        # T3: Gaps found via inline verify — bypass only the independent_review gate
        # failure. The original WO closes with gaps registered; the gap WO remediates.
        # Skipped for escalated WOs: a gappy (failed) review is not the required pass.
        if _has_gaps and not _is_escalated:
            gate_failures = [f for f in gate_failures if not f.startswith("independent_review")]

        # WO-REVIEW-TRACEABILITY: Unreviewable + passing AC gate → close proceeds.
        # The AC gate is the authoritative close blocker. When the grader is unreviewable
        # (no commit evidence) but all executable checks pass, the independent_review
        # gate failure is advisory only — bypass it so close is not hard-blocked.
        # Unreviewable + failing/missing AC → the AC gate failure still blocks close.
        # Skipped for escalated WOs: re-close demands a genuine passing review, not an
        # unreviewable verdict (WO-ESCALATION-LADDER T3).
        _is_unreviewable = (
            _verify_ran and _verify_result is not None and _verify_result.get("unreviewable")
        )
        if _is_unreviewable and not ac_failures and not _is_escalated:
            gate_failures = [f for f in gate_failures if not f.startswith("independent_review")]

        # T3: mandatory review for escalated WOs — independent_review failures block
        # the close even under force. force may still bypass OTHER gates, but it can
        # never silently re-close an escalated WO whose adversarial review did not pass.
        if _is_escalated:
            _ir_failures = [f for f in gate_failures if f.startswith("independent_review")]
            if _ir_failures:
                return {
                    "ok": False,
                    "error": (
                        "Escalated work order requires a passing independent review before "
                        "re-close — this gate cannot be bypassed with force."
                    ),
                    "failures": _ir_failures,
                    "escalated": True,
                }

        if gate_failures and not force:
            return {
                "ok": False,
                "error": "Gate check failed",
                "failures": gate_failures,
            }

        now = datetime.now(UTC).isoformat()

        if force and gate_failures:
            for reason in gate_failures:
                try:
                    import spool.writer as _spool_writer

                    from canonical.events.envelope import CanonicalEventEnvelope

                    envelope = CanonicalEventEnvelope(
                        event_type="gate.bypassed",
                        session_id=None,
                        payload={
                            "work_order_id": work_order_id,
                            "gate": reason.split(":")[0],
                            "reason": reason,
                        },
                        timestamp=now,
                        severity="warning",
                        trace={
                            "domain": "sdlc",
                            "work_order_id": work_order_id,
                            "milestone_id": wo_milestone_id,
                            "project_id": project_id,
                            "attribution_status": "fully_attributed",
                        },
                    )
                    _spool_writer.write_event(envelope.to_dict())
                except Exception:
                    pass

        try:
            import spool.writer as _spool_writer

            from canonical.events.envelope import CanonicalEventEnvelope

            envelope = CanonicalEventEnvelope(
                event_type="work_order.closed",
                session_id=None,
                payload={
                    "work_order_id": work_order_id,
                    "title": title,
                    "project_id": project_id,
                    "forced": force,
                },
                timestamp=now,
                severity="info",
                trace={
                    "domain": "sdlc",
                    "work_order_id": work_order_id,
                    "milestone_id": wo_milestone_id,
                    "project_id": project_id,
                    "attribution_status": "fully_attributed",
                },
            )
            _spool_writer.write_event(envelope.to_dict())
        except Exception:
            pass

        conn.execute(
            "UPDATE business_work_orders"
            " SET status = 'closed', closed_at = ?, updated_at = ?, last_updated_at = ?"
            " WHERE work_order_id = ?",
            (now, now, now, work_order_id),
        )

        next_wo: dict[str, Any] | None = None
        milestone_complete = False
        if wo_milestone_id:
            next_row = conn.execute(
                "SELECT work_order_id, title, work_order_type, sequence_order"
                " FROM business_work_orders"
                " WHERE milestone_id = ? AND work_order_id != ? AND status = 'created'"
                " ORDER BY sequence_order ASC NULLS LAST, created_at ASC LIMIT 1",
                (wo_milestone_id, work_order_id),
            ).fetchone()
            if next_row:
                next_wo = {
                    "work_order_id": next_row[0],
                    "title": next_row[1],
                    "type": next_row[2],
                    "sequence_order": next_row[3],
                    "next_command": f"ds work-order start {next_row[0]}",
                }
            else:
                remaining = conn.execute(
                    "SELECT COUNT(*) FROM business_work_orders"
                    " WHERE milestone_id = ? AND work_order_id != ?"
                    f" AND status NOT IN ({terminal_wo_status_placeholders()})",
                    (wo_milestone_id, work_order_id, *TERMINAL_WO_STATUSES),
                ).fetchone()[0]
                if remaining == 0:
                    milestone_complete = True

    result: dict[str, Any] = {
        "ok": True,
        "work_order_id": work_order_id,
        "title": title,
        "status": "closed",
        "forced": force,
        "bypassed_gates": gate_failures if force else [],
    }
    if _verify_ran and _verify_result is not None and _verify_result.get("unreviewable"):
        result["verify_warning"] = _verify_result.get("summary") or (
            "independent review unreviewable: no commit evidence found."
        )
        _unreviewable_graders = _verify_result.get("unreviewable_graders")
        if _unreviewable_graders:
            result["unreviewable_graders"] = _unreviewable_graders
    if next_wo:
        result["next_work_order"] = next_wo
        result["next_command"] = next_wo["next_command"]
        seq = next_wo.get("sequence_order")
        seq_str = f" (seq={seq})" if seq is not None else ""
        next_id = next_wo["work_order_id"]
        next_title = next_wo["title"]
        result["next_block"] = (
            f"NEXT WORK ORDER: {next_title}{seq_str}"
            f" / ID: {next_id}"
            f" / Run: py -m interfaces.cli.ds work-order start {next_id}"
        )
    elif milestone_complete and wo_milestone_id:
        result["milestone_complete"] = True
        result["milestone_id"] = wo_milestone_id
        result["next_command"] = f"ds milestone close {wo_milestone_id}"
        result["next_block"] = (
            f"MILESTONE COMPLETE / Run: py -m interfaces.cli.ds milestone close {wo_milestone_id}"
        )
    else:
        result["next_block"] = "NO NEXT WORK ORDER FOUND"

    # Report-only continuation (WO-CLOSE-REPORT-ONLY): advertise the next ready WO
    # (or the registered remediation WOs) via _apply_report_only_continuation — see
    # close_continuation.py for the full rationale (extracted verbatim; called here
    # where the inline block used to sit). Close deliberately does NOT auto-start
    # anything.
    _apply_report_only_continuation(
        result,
        verify_ran=_verify_ran,
        verify_result=_verify_result,
        project_id_for_autostart=_project_id_for_autostart,
        has_gaps=_has_gaps,
        title=title,
        work_order_id=work_order_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )

    # Flush the work_order.closed spool event through the projection pipeline so
    # callers see status='closed' in the read model without a manual sync_tick.
    # Best-effort — a transient projection failure degrades to the daemon's next cycle.
    try:
        from core.projections.runner import sync_tick as _sync_tick_post

        _sync_tick_post()
    except Exception:
        pass

    return result
