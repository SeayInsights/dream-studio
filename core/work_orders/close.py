"""Work-order close: run pre/post gates, mutate to complete, surface next step.

This module replaces the monolithic `_work_order_close` handler that lived in
`interfaces/cli/ds.py`. It decomposes the work into three composable,
side-effect-aware functions so skills, workflows, and hooks can call them
directly without going through the CLI subprocess:

- `run_gate_check(gate_name, planning_root=, work_order_id=, project_id=, conn=)`
    The per-gate predicate. Pure read against the planning artifact tree and
    the (caller-owned) SQLite connection. Returns `(passed, failure_reason)`.
    Moved verbatim from ds.py so the predicate semantics stay identical.

- `check_close_gates(work_order_id=, source_root=, dream_studio_home=,
                      planning_root=)`
    Pure read. Opens its own connection, looks up the work order and its
    type, evaluates every gate (pre|post split on `|`), and returns a dict
    with the WO metadata, the gate list, and the failures. Does NOT mutate
    state or emit spool events. Skills/workflows call this to preview
    whether a close would succeed.

- `close_work_order(work_order_id=, force=False, source_root=,
                     dream_studio_home=, planning_root=)`
    Composer. Re-runs the gate evaluation inside the same connection that
    performs the status mutation, so the gate→close transition is atomic.
    Emits the `gate.bypassed` spool event(s) when `force=True` is used to
    override failures, emits `work_order.closed`, updates the row to
    complete, and computes the next-step hint (next open WO in the same
    milestone, or milestone-complete signal). Returns a result dict with
    the canonical shape — no `print()`, no `sys.exit`.

The stderr `[gate.bypassed] WARNING:` line that used to be emitted from
this handler is REMOVED from the pure path. The CLI wrapper in ds.py
re-emits it from the returned `bypassed_gates` list so operator-terminal
behavior stays identical.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect


def _require_db(source_root: Path, dream_studio_home: Path | None) -> Path:
    # Lazy import via ds.py — see core.work_orders.start._require_db for rationale.
    from interfaces.cli.ds import resolve_installed_runtime_paths

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing. Run rehearsal-install first.")
    return paths.sqlite_path


def run_gate_check(
    gate_name: str | None,
    *,
    planning_root: Path,
    work_order_id: str,
    project_id: str,
    conn: Any,
) -> tuple[bool, str]:
    """Return (passed, failure_reason). failure_reason is empty string when passed=True."""
    if not gate_name:
        return True, ""

    wo_dir = planning_root / "work-orders" / work_order_id

    if gate_name == "design_brief_locked":
        try:
            row = conn.execute(
                "SELECT 1 FROM business_design_briefs"
                " WHERE project_id = ? AND status = 'locked' LIMIT 1",
                (project_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            try:
                row = conn.execute(
                    "SELECT 1 FROM ds_documents"
                    " WHERE doc_type = 'design_brief' AND project_id = ? LIMIT 1",
                    (project_id,),
                ).fetchone()
            except sqlite3.OperationalError:
                row = None
        if row is None:
            return False, "design_brief_locked: no locked design brief found for this project"
        return True, ""

    if gate_name == "api_contract_exists":
        if not (wo_dir / "api-contract.md").is_file():
            return False, "api_contract_exists: api-contract.md not found"
        return True, ""

    if gate_name == "api_contract_and_security_review":
        if not (wo_dir / "api-contract.md").is_file():
            return False, "api_contract_and_security_review: api-contract.md not found"
        if not (wo_dir / "security-scan.md").is_file():
            return False, "api_contract_and_security_review: security-scan.md not found"
        return True, ""

    if gate_name == "spec_approved":
        if not (wo_dir / "spec.md").is_file():
            return False, "spec_approved: spec.md not found"
        return True, ""

    if gate_name == "all_tests_pass":
        results_path = wo_dir / "test-results.md"
        if not results_path.is_file():
            return False, "all_tests_pass: test-results.md not found"
        content = results_path.read_text(encoding="utf-8")
        if "PASSED" not in content.upper():
            return False, "all_tests_pass: test-results.md does not contain PASSED"
        return True, ""

    if gate_name == "design_critique":
        import re as _re

        critique_path = wo_dir / "design-critique.md"
        if not critique_path.is_file():
            return False, "design_critique: design-critique.md not found"
        content = critique_path.read_text(encoding="utf-8")
        match = _re.search(r"Score:\s*(\d+)/(\d+)", content)
        if not match:
            return False, "design_critique: no 'Score: N/M' found in design-critique.md"
        score = int(match.group(1))
        if score < 3:
            return False, f"design_critique: score {score} is below minimum 3"
        return True, ""

    if gate_name == "security_scan":
        scan_path = wo_dir / "security-scan.md"
        if not scan_path.is_file():
            return False, "security_scan: security-scan.md not found"
        content = scan_path.read_text(encoding="utf-8")
        if "BLOCKED" in content.upper():
            return False, "security_scan: security-scan.md contains BLOCKED"
        return True, ""

    if gate_name == "game_validate":
        if not (wo_dir / "game-validate.md").is_file():
            return False, "game_validate: game-validate.md not found"
        return True, ""

    if gate_name == "anti_slop_passed":
        lint_path = wo_dir / "lint-results.md"
        if not lint_path.is_file():
            return False, (
                f"anti_slop_passed: lint-results.md not found. Run: python "
                f"canonical/skills/domains/modes/website/scripts/lint-artifact.py "
                f"<artifact_path> > .planning/work-orders/{work_order_id}/lint-results.md"
            )
        _lint_content = lint_path.read_text(encoding="utf-8")
        if "BLOCKED" in _lint_content.upper():
            return False, "anti_slop_passed: lint-results.md contains BLOCKED"
        if "PASSED" not in _lint_content.upper():
            return False, "anti_slop_passed: lint-results.md does not contain PASSED"
        return True, ""

    if gate_name == "independent_review_passed":
        review_path = wo_dir / "independent-review.md"
        if not review_path.is_file():
            return False, (
                "independent_review_passed: independent-review.md not found. "
                "The execute-work-orders workflow writes this via the independent-review node."
            )
        content = review_path.read_text(encoding="utf-8")
        if "VERDICT: PASS" not in content.upper().replace(" ", "").replace("\n", ""):
            # Accept both "VERDICT: PASS" and "VERDICT:PASS"
            import re as _re

            if not _re.search(r"VERDICT\s*:\s*PASS", content, _re.IGNORECASE):
                return (
                    False,
                    "independent_review_passed: independent-review.md does not contain 'VERDICT: PASS'",
                )
        return True, ""

    if gate_name == "independent_review":
        import json as _json

        verdict_path = wo_dir / "review-verdict.json"
        if not verdict_path.is_file():
            return False, (
                f"independent_review: review-verdict.json not found. "
                f"Run: py -m interfaces.cli.ds work-order verify {work_order_id}"
            )
        try:
            verdict = _json.loads(verdict_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return False, f"independent_review: review-verdict.json is not valid JSON: {exc}"
        if not verdict.get("passed"):
            gap_ids = [w.get("work_order_id", "") for w in verdict.get("spawned_work_orders", [])]
            gap_msg = f" Gap WOs: {', '.join(gap_ids)}" if gap_ids else ""
            return False, (
                f"independent_review: review failed — {verdict.get('summary', 'no summary')}.{gap_msg}"
            )
        return True, ""

    return True, ""


def _lookup_work_order_and_gates(conn: Any, work_order_id: str) -> dict[str, Any]:
    """Internal helper: read WO row + type row, return everything close needs.

    Returns either ``{"ok": False, "error": ...}`` or a dict with keys:
    ``work_order_id, title, wo_status, type_id, project_id, milestone_id,
    pre_gate, post_gate``.
    """

    wo_row = conn.execute(
        "SELECT work_order_id, title, status, work_order_type, project_id, milestone_id"
        " FROM business_work_orders WHERE work_order_id = ?",
        (work_order_id,),
    ).fetchone()
    if wo_row is None:
        return {"ok": False, "error": f"Work order not found: {work_order_id}"}

    wo_id, title, wo_status, wo_type, project_id, milestone_id = wo_row

    pre_gate = None
    post_gate = None
    if wo_type:
        type_row = conn.execute(
            "SELECT pre_build_gate, build_executor, post_build_gate"
            " FROM business_work_order_types WHERE type_id = ?",
            (wo_type,),
        ).fetchone()
        if type_row is not None:
            pre_gate = type_row[0]
            post_gate = type_row[2]

    return {
        "ok": True,
        "work_order_id": wo_id,
        "title": title,
        "wo_status": wo_status,
        "type_id": wo_type,
        "project_id": project_id,
        "milestone_id": milestone_id,
        "pre_gate": pre_gate,
        "post_gate": post_gate,
    }


def _evaluate_gates(
    conn: Any,
    *,
    pre_gate: str | None,
    post_gate: str | None,
    work_order_id: str,
    project_id: str,
    planning_root: Path,
) -> list[str]:
    """Run pre+post gate checks (split on ``|``). Return list of failure reasons."""

    failures: list[str] = []
    gates_to_check: list[str] = []
    for raw_gate in (pre_gate, post_gate):
        if raw_gate:
            gates_to_check.extend(raw_gate.split("|"))
    for gate_name in gates_to_check:
        passed, reason = run_gate_check(
            gate_name,
            planning_root=planning_root,
            work_order_id=work_order_id,
            project_id=project_id,
            conn=conn,
        )
        if not passed:
            failures.append(reason)
    return failures


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
        )

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
        _verdict_path = p_root / "work-orders" / work_order_id / "review-verdict.json"
        if not _verdict_path.is_file():
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
        )

        # T3: Gaps found via inline verify — bypass only the independent_review gate
        # failure. The original WO closes with gaps registered; the gap WO remediates.
        if _has_gaps:
            gate_failures = [f for f in gate_failures if not f.startswith("independent_review")]

        if gate_failures and not force:
            return {
                "ok": False,
                "error": "Gate check failed",
                "failures": gate_failures,
            }

        now = datetime.now(timezone.utc).isoformat()

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
                    " AND status NOT IN ('closed', 'cancelled')",
                    (wo_milestone_id, work_order_id),
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

    # T2/T4: Auto-start after close when verify ran inline.
    if _verify_ran and _verify_result is not None and _project_id_for_autostart:
        if _has_gaps:
            # T4: Print GAPS FOUND block; T2: auto-start the first spawned gap WO.
            spawned = _verify_result.get("spawned_work_orders", [])
            if spawned:
                first_gap = spawned[0]
                gap_wo_id = first_gap["work_order_id"]
                gap_wo_title = first_gap["title"]
                gaps_list = _verify_result.get("gaps", [])
                tasks_str = "\n".join(f"  - {g.get('title', '')}" for g in gaps_list)
                _sep = "=" * 42
                result["gaps_block"] = (
                    f"\n{_sep}\n"
                    f"=== GAPS FOUND IN {title} ===\n"
                    f"Registered: REMEDIATION WO {gap_wo_id} with {len(gaps_list)} tasks\n"
                    f"Tasks:\n{tasks_str}\n"
                    f"AUTO-STARTING remediation WO next.\n"
                    f"Main session: review "
                    f".planning/work-orders/{work_order_id}/review-verdict.json for full detail.\n"
                    f"{_sep}\n"
                )
                result["spawned_work_orders"] = spawned
                from core.work_orders.start import start_work_order as _start_wo

                _started = _start_wo(
                    work_order_id=gap_wo_id,
                    source_root=source_root,
                    dream_studio_home=dream_studio_home,
                    planning_root=p_root,
                    accept_no_brief=True,
                )
                if _started.get("ok"):
                    result["auto_started"] = {
                        "work_order_id": gap_wo_id,
                        "title": gap_wo_title,
                        "message": f"AUTO-STARTING: {gap_wo_title} / ID: {gap_wo_id}",
                    }
                else:
                    result["auto_start_error"] = _started.get("error", "unknown error")
        else:
            # T2: Verify passed — find and auto-start the next WO in the project.
            from core.projects.queries import get_next_work_order as _get_next
            from core.work_orders.start import start_work_order as _start_wo

            _next_result = _get_next(
                project_id=_project_id_for_autostart,
                source_root=source_root,
                dream_studio_home=dream_studio_home,
            )
            _next_wo = _next_result.get("work_order") if _next_result.get("ok") else None
            if _next_wo:
                _next_id = _next_wo["work_order_id"]
                _next_title = _next_wo["title"]
                _started = _start_wo(
                    work_order_id=_next_id,
                    source_root=source_root,
                    dream_studio_home=dream_studio_home,
                    planning_root=p_root,
                    accept_no_brief=True,
                )
                if _started.get("ok"):
                    result["auto_started"] = {
                        "work_order_id": _next_id,
                        "title": _next_title,
                        "message": f"AUTO-STARTING: {_next_title} / ID: {_next_id}",
                    }
                else:
                    result["auto_start_error"] = _started.get("error", "unknown error")
            else:
                result["auto_start_message"] = "MILESTONE COMPLETE"

    return result
