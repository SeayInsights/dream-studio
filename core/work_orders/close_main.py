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

import json
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

# WO-GRADER-ADVERSARIAL: independent review is default-on at close for every WO
# type except these (no code to review — their deliverable is the document, and
# the executable_ac / attestation path covers them).
_VERIFY_EXEMPT_TYPES = frozenset({"documentation"})


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

        # R5 T1: change-impact affirmation preview (universal; pre-cutover WOs grandfathered).
        from core.gates.change_impact import check_change_impact_affirmed

        failures.extend(check_change_impact_affirmed(conn, work_order_id, db_path))

        # WO-WO-LIFECYCLE-SURFACE: the structural invariants, previewed HERE as well as
        # enforced in close_work_order. A preview that omits a blocking gate is worse than
        # no preview: it tells an author they are ready to close and then the close
        # refuses. See the rationale at the enforcement site below.
        from core.work_orders.structural_invariants import (
            check_structure,
            recorded_exception,
        )
        from core.work_orders.structural_invariants import render as _render_structure

        _structure_preview = check_structure(work_order_id, db_path=db_path)
        if _structure_preview and not recorded_exception(work_order_id, db_path=db_path):
            failures.append(_render_structure(_structure_preview, work_order_id))

    meta["gate_failures"] = failures
    meta["gates_pass"] = not failures
    return meta


def _ledger_verdict_mismatch(
    ledger: dict[str, Any],
    work_order_id: str,
    *,
    planning_root: Path,
    db_path: Path | None,
) -> str:
    """Note text when the residual-risk ledger came from a DIFFERENT verify run
    than the stored verdict — else an empty string.

    Gap WO 72b19987 task 3. The ledger and the verdict are persisted to two stores
    in sequence, and that window cannot be closed without a cross-store
    transaction, so the pair must at least be DETECTABLE. Carrying the run stamp
    made it *recordable*; this reader is what makes it *detected*. Recording a
    signal nobody consumes leaves the mismatch exactly as invisible as it was —
    the same engine-key-with-no-reader shape this milestone keeps finding.

    Silent (returns "") whenever the comparison cannot be made: an absent stamp on
    either side is a pre-stamp artifact, not evidence of a mismatch. Never raises —
    this decorates an advisory note and must not be able to block a close.
    """
    try:
        ledger_at = ledger.get("verified_at")
        if not isinstance(ledger_at, str) or not ledger_at:
            return ""  # pre-stamp ledger: absence is not a mismatch

        from core.work_orders.artifacts import get_wo_artifact_envelope

        raw, _envelope = get_wo_artifact_envelope(work_order_id, "review_verdict", db_path=db_path)
        if raw is None:
            disk = planning_root / "work-orders" / work_order_id / "review-verdict.json"
            raw = disk.read_text(encoding="utf-8") if disk.is_file() else None
        if not raw:
            return ""
        payload = json.loads(raw)
        # An enveloped artifact carries the verdict as a JSON string in `content`.
        if isinstance(payload, dict) and isinstance(payload.get("content"), str):
            payload = json.loads(payload["content"])
        if not isinstance(payload, dict):
            return ""
        verdict_at = payload.get("completed_at") or payload.get("verified_at")
        if not isinstance(verdict_at, str) or not verdict_at:
            return ""
        if verdict_at == ledger_at:
            return ""
        return (
            " NOTE: this residual-risk list is from a different verify run than the stored"
            f" verdict (ledger {ledger_at}, verdict {verdict_at}) — one of the two writes did"
            " not complete. Re-run `ds work-order verify` so both describe the same run."
        )
    except Exception:
        return ""  # a decoration must never break the note it decorates


def close_work_order(
    *,
    work_order_id: str,
    force: bool = False,
    skip_verify: bool = False,
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

    # WO-BOUNDARY-OPEN-END: pin the boundary's end BEFORE anything grades this work order.
    #
    # THE ORDERING IS THE WHOLE POINT, and the first cut got it wrong. The stamp sat after
    # the status mutation, ~300 lines below the auto-verify -- so the verify that GATES
    # this close still graded an unbounded `<start>..HEAD` range, which is the exact
    # failure mode this work order exists to remove. Its own independent review caught it:
    # "close runs verify (:234) long before it stamps (:528)".
    #
    # Stamping here means the range is `<start>..<the commit the work finished at>` for
    # the gating verify, for any re-verify, and for every later read of the boundary.
    #
    # Best-effort, like the start stamp: a close must not fail on bookkeeping. A boundary
    # that cannot be pinned keeps its open range AND says so.
    # TWO INDEPENDENT OPERATIONS, TWO TRY BLOCKS. They shared one, so a boundary pin that
    # raised skipped the ownership record entirely -- and the two are not related: one
    # narrows the window, the other claims the commits inside it.
    #
    # AND THE FAILURES ARE REPORTED. The comment above already promised that a boundary
    # which cannot be pinned "keeps its open range AND says so", while the code said
    # nothing at all: `except Exception: pass`. Best-effort means the close proceeds, not
    # that the operator is left to discover an unattributed work order later, from a
    # verify that grades the wrong range. mark_task_done already reports its equivalent
    # failure as `commit_ownership_error`; close was the site that stayed quiet.
    _bookkeeping_errors: dict[str, str] = {}
    try:
        from .delivery_boundary import record_delivery_boundary_end
        from .verify_executor import resolve_project_root

        record_delivery_boundary_end(
            work_order_id,
            repo_root=resolve_project_root(work_order_id, db_path),
            db_path=db_path,
        )
    except Exception as _exc:  # noqa: BLE001 - closing must not fail on bookkeeping
        _bookkeeping_errors["delivery_boundary_error"] = f"{type(_exc).__name__}: {_exc}"[:200]

    # WO 80c0e61b: claim the commits, so a later reader can tell this work order's work
    # from a branch neighbour's. Pinning the end alone narrows the WINDOW; only per-commit
    # ownership survives two work orders sharing one.
    try:
        from .range_attribution import record_commit_ownership
        from .verify_executor import resolve_project_root

        record_commit_ownership(
            work_order_id,
            repo_root=resolve_project_root(work_order_id, db_path),
            db_path=db_path,
        )
    except Exception as _exc:  # noqa: BLE001 - closing must not fail on bookkeeping
        _bookkeeping_errors["commit_ownership_error"] = f"{type(_exc).__name__}: {_exc}"[:200]

    # BOOKKEEPING FAILURES TRAVEL WITH EVERY EXIT, not only the successful one.
    # `_bookkeeping_errors` was merged into the success result ~400 lines below and five
    # returns sit in between -- including `if gate_failures and not force`, the NORMAL
    # blocked-close outcome. So an unpinned boundary or unrecorded ownership was reported
    # only on a close that had already succeeded: the case where it matters least. The
    # test meant to cover this passed force=True to get past the gates, which is the one
    # path that already worked (WO b302834b task cb64fa0a).
    with _connect(db_path) as _pre_conn:
        _pre_meta = _lookup_work_order_and_gates(_pre_conn, work_order_id)
    if not _pre_meta.get("ok"):
        return {**_pre_meta, **_bookkeeping_errors}

    _post_gate_str = _pre_meta.get("post_gate") or ""
    _ir_in_post = "independent_review" in [
        g.strip() for g in _post_gate_str.split("|") if g.strip()
    ]
    # WO-GRADER-ADVERSARIAL (operator directive 2026-08-18: capabilities fire on
    # relevance, asking optional): independent review is DEFAULT-ON for every WO
    # type except documentation — previously it ran only for types whose post-gate
    # named independent_review, so most code WOs closed with zero review. Opting
    # out requires the explicit skip_verify flag and is recorded as a gate bypass.
    _verify_default_on = (_pre_meta.get("type_id") or "") not in _VERIFY_EXEMPT_TYPES
    if _ir_in_post or _verify_default_on:
        # WO-FILESDB-C2: a verdict may live in the authority (DB) or on the .planning
        # disk fallback — check both before triggering an inline re-verify.
        from core.work_orders.artifacts import has_wo_artifact as _has_verdict

        _verdict_path = p_root / "work-orders" / work_order_id / "review-verdict.json"
        _verdict_exists = (
            _has_verdict(work_order_id, "review_verdict", db_path=db_path)
            or _verdict_path.is_file()
        )
        if not _verdict_exists and skip_verify:
            # The escape hatch works — and leaves a mark (WO-BYPASS-TELEMETRY).
            from core.gates.bypass_event import record_gate_bypass

            record_gate_bypass(
                "independent_review",
                f"skip_verify: close of {work_order_id} proceeded without independent review",
                extra={"work_order_id": work_order_id},
            )
        elif not _verdict_exists:
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
                    **_bookkeeping_errors,
                    "ok": False,
                    "error": f"Auto-verify raised an exception: {exc}",
                }
            if _verify_result.get("ok"):
                _verify_ran = True
            else:
                # WO-GRADER-ADVERSARIAL: verify could not run at all (e.g. the WO
                # has no tasks). Do NOT hard-fail the close with an opaque verify
                # error — fall through so the gates report the ACTUAL failures
                # (missing verdict, tasks_done, executable_ac), which are the
                # actionable ones. _verify_ran stays False so the unreviewable/
                # gaps bypasses below cannot misfire on a non-verdict.
                _verify_result = None

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
            return {**meta, **_bookkeeping_errors}

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

        # WO-GRADER-ADVERSARIAL: the independent_review gate applies to every
        # non-exempt WO type, not only those whose type post-gate names it —
        # previously api_endpoint/ui/saas/pipeline WOs closed with zero review.
        # skip_verify (recorded as a gate bypass above) waives it for this close;
        # the unreviewable+AC and gaps bypasses below keep their existing semantics.
        if _verify_default_on and not _ir_in_post and not skip_verify:
            from .close_gates import run_gate_check as _run_ir_gate

            _ir_ok, _ir_reason = _run_ir_gate(
                "independent_review",
                planning_root=p_root,
                work_order_id=work_order_id,
                project_id=project_id,
                conn=conn,
                db_path=db_path,
            )
            if not _ir_ok:
                gate_failures.append(_ir_reason)

        # Always-on AC gate: run all executable checks across every task.
        # Runs regardless of WO type; additional to (not replacing) the existing gates.
        _ac_stats: dict[str, Any] = {}
        ac_failures = _run_ac_gate(
            conn, work_order_id=work_order_id, db_path=db_path, stats=_ac_stats
        )
        gate_failures.extend(ac_failures)

        # Re-run the originating symptom SQL-CHECK (if captured at registration).
        # A still-failing symptom means the fix never landed — block close unless forced.
        # WO-CI-COMPLETENESS: the checks are also surfaced VERBATIM with their live
        # results (symptom_checks in the result dict, incl. a trivially_true flag for
        # FROM-less SQL) so a decorative symptom is visible to the operator at close.
        _orig_symptom = meta.get("originating_symptom")
        _symptom_checks: list[dict[str, Any]] = []
        if _orig_symptom:
            _sym_failure = _check_originating_symptom(_orig_symptom, db_path)
            if _sym_failure:
                gate_failures.append(_sym_failure)
            try:
                from .close_gates import symptom_check_detail
                from .verify_executor import resolve_project_root as _rpr

                _symptom_checks = symptom_check_detail(
                    _orig_symptom,
                    db_path,
                    work_order_id=work_order_id,
                    project_root=_rpr(work_order_id, db_path) or source_root,
                    title=title,
                )
            except Exception:
                _symptom_checks = []

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

        # WO-WO-LIFECYCLE-SURFACE: THE TWO STRUCTURAL INVARIANTS. Operator ruling — a work
        # order should ALWAYS have multiple tasks; a milestone should ALWAYS have more than
        # one work order. Measured 2026-08-28 against THIS gate's own counting — every task,
        # every sibling, not just the open ones: of 128 open work orders, 49 carry one task
        # or none and 4 sit in a milestone with no sibling. 52 distinct work orders would be
        # refused. Nothing had ever refused one.
        #
        # Refused HERE and not at creation or start. A work order has zero tasks when it is
        # created and often still has zero when it is started — ds-project decomposes only
        # the first work order of the first milestone and the rest "get tasks when they are
        # started". Close is the first moment the count is a fact rather than a not-yet: it
        # is where "this work order is done" gets claimed, and one task is a claim about a
        # unit that was mis-sized.
        #
        # The escape is a recorded reason (`--accept-structure`), not `--force`, which
        # bypasses every gate at once and records no reasoning about this one.
        from core.work_orders.structural_invariants import (
            check_structure,
            recorded_exception,
        )
        from core.work_orders.structural_invariants import render as _render_structure

        _structure = check_structure(work_order_id, db_path=db_path)
        if _structure and not recorded_exception(work_order_id, db_path=db_path):
            gate_failures.append(_render_structure(_structure, work_order_id))

        # R5 T1: change-impact affirmation — a WO created on/after the cutover must record
        # an impact affirmation (auth/contract/migration/changelog) before close. Universal
        # and WO-type agnostic; pre-cutover WOs are grandfathered. Like tasks_done it is not
        # subject to the independent_review bypass; a forced close records a gate.bypassed.
        # See CLAUDE.md's Code History & Impact Guardrail.
        from core.gates.change_impact import check_change_impact_affirmed

        gate_failures.extend(check_change_impact_affirmed(conn, work_order_id, db_path))

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
                    **_bookkeeping_errors,
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
                **_bookkeeping_errors,
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
    if _symptom_checks:
        result["symptom_checks"] = _symptom_checks
    # Bookkeeping that did not land is stated, not swallowed. An unrecorded boundary or
    # ownership set does not block the close -- it makes a later verify grade a wider
    # range than it should, which is a thing the operator can only act on if told.
    result.update(_bookkeeping_errors)

    # WO-SEPARATE-TEST-RUNNER gap (e3a17189): a close whose review certified by
    # READING must not read the same as one a test run backs. all_tests_pass
    # executes the WO's own checks, but an attested WO or one with no TEST-CHECK
    # registered can still reach here — and "closed" then implies execution that
    # never happened. Advisory: it states the basis, it does not block.
    try:
        from core.gates.merge_readiness import work_order_execution_caveat

        # checks_ran_here is EARNED, and it is measured at the place that actually
        # runs them: the ALWAYS-ON AC gate above, which executes every TEST-CHECK on
        # every close regardless of WO type. Two wrong versions preceded this one —
        # asserting True unconditionally (a forced close bypasses execution and would
        # have gone silent about it), then deriving it from the type's
        # `all_tests_pass` gate, which most WO types do not list. The second printed
        # a FALSE caveat on this feature's own clean close: "none ran during verify",
        # moments after the AC gate had run all three. Counting what ran cannot be
        # wrong in either direction.
        _tests_gate_ran = int(_ac_stats.get("test_checks_executed") or 0) > 0
        _exec_caveat = work_order_execution_caveat(
            work_order_id,
            db_path=db_path,
            planning_root=p_root,
            checks_ran_here=_tests_gate_ran,
        )
        if _exec_caveat:
            result["test_execution_warning"] = _exec_caveat

        # WO-GAP-FANOUT: the attach-loop bound, surfaced where work is declared done.
        from core.gates.merge_readiness import work_order_attachment_pressure

        _pressure = work_order_attachment_pressure(
            work_order_id, db_path=db_path, planning_root=p_root
        )
        if _pressure:
            result["attachment_pressure"] = _pressure
    except Exception:
        pass  # an advisory must never affect a close

    # WO-MAINRED-VISIBILITY: a WO must not be declared done while its own merge
    # has main red without the operator seeing it. Advisory only — never blocks,
    # never alters a gate outcome; an unknown status stays silent rather than
    # crying wolf.
    try:
        from core.health.main_ci import main_ci_status, main_ci_warning

        # WO-MAINCI-CACHE: close reads LIVE (max_age_seconds=0). doctor and
        # project state accept a short-TTL cached answer because they run
        # constantly; declaring work done is the one low-frequency,
        # high-consequence moment that must not be told about main by a cache.
        _main_ci = main_ci_status(repo_root=source_root, max_age_seconds=0)
        _warning = main_ci_warning(_main_ci)
        if _warning:
            result["main_ci_warning"] = _warning
            result["main_ci"] = _main_ci
    except Exception:
        pass  # status reporting must never affect a close

    # WO-FALSIFY-FIRST-PASS: surface the WO's open UNVERIFIED risk ledger at
    # close. A residual risk the falsification analyst could not test must be
    # visible when the WO is declared done — otherwise "closed" reads as "no
    # known risk", which is exactly the silence this milestone removes.
    try:
        from core.work_orders.verify_persist import read_unverified_ledger

        _ledger = read_unverified_ledger(work_order_id, planning_root=p_root, db_path=db_path)
        if _ledger and _ledger.get("unreadable"):
            # A ledger that exists but cannot be read is NOT zero residual risk.
            result["unverified_risks_note"] = (
                f"residual-risk ledger could not be read — {_ledger['unreadable']}."
                " Re-run: py -m interfaces.cli.ds work-order verify " + work_order_id
            )
        elif _ledger and _ledger.get("unverified"):
            result["unverified_risks"] = _ledger["unverified"]
            _partial = (
                " The analysis was PARTIAL (diff truncated), so this list may be incomplete."
                if _ledger.get("truncated")
                else ""
            )
            # PAIRING CHECK (gap WO 72b19987 task 3, caught by that WO's own
            # re-verify): the ledger and the verdict are written to two stores in
            # sequence, so a crash between them pairs run N's ledger with run
            # N-1's verdict. Carrying the run stamp made that RECORDABLE — but
            # nothing read it, so "detectable" was latent data and the mismatch
            # stayed as invisible as before. Something has to do the comparing.
            _stale_pair = _ledger_verdict_mismatch(
                _ledger, work_order_id, planning_root=p_root, db_path=db_path
            )
            result["unverified_risks_note"] = (
                f"{len(_ledger['unverified'])} worst-case scenario(s) remain UNVERIFIED for"
                f" this work order — residual risk recorded, not resolved.{_partial}{_stale_pair}"
            )
    except Exception as exc:  # noqa: BLE001 - surfacing must not block the close
        # But it must not vanish either: a failed read is reported, not swallowed
        # (quality rule 2, caught by this stage's own verify).
        result["unverified_risks_note"] = (
            f"residual-risk ledger surfacing failed: {type(exc).__name__}: {str(exc)[:200]}"
        )
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
