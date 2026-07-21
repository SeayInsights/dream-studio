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
from datetime import datetime, UTC
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


def _artifact_text(work_order_id: str, wo_dir: Path, kind: str, db_path: Path | None) -> str | None:
    """WO ceremony artifact content — authority table first, .planning disk fallback.

    WO-FILESDB-P1: artifacts moved into business_work_order_artifacts. The disk
    fallback keeps historical WOs (and the live authority DB before the migration
    is activated) gate-satisfiable during the transition.
    """
    from core.work_orders.artifacts import KIND_TO_FILENAME, get_wo_artifact

    content = get_wo_artifact(work_order_id, kind, db_path=db_path)
    if content is not None:
        return content
    fpath = wo_dir / KIND_TO_FILENAME[kind]
    if fpath.is_file():
        return fpath.read_text(encoding="utf-8")
    return None


def run_gate_check(
    gate_name: str | None,
    *,
    planning_root: Path,
    work_order_id: str,
    project_id: str,
    conn: Any,
    db_path: Path | None = None,
) -> tuple[bool, str]:
    """Return (passed, failure_reason). failure_reason is empty string when passed=True.

    The optional ``db_path`` argument is used by the ``all_tests_pass`` gate to
    execute TEST-CHECKs from the WO's task acceptance criteria.  Callers that
    don't hold a db_path (e.g. tests that invoke run_gate_check directly) may omit
    it; in that case the gate falls back to the legacy file-presence check.
    """
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
        if _artifact_text(work_order_id, wo_dir, "api_contract", db_path) is None:
            return False, "api_contract_exists: api-contract.md not found"
        return True, ""

    if gate_name == "api_contract_and_security_review":
        if _artifact_text(work_order_id, wo_dir, "api_contract", db_path) is None:
            return False, "api_contract_and_security_review: api-contract.md not found"
        if _artifact_text(work_order_id, wo_dir, "security_scan", db_path) is None:
            return False, "api_contract_and_security_review: security-scan.md not found"
        return True, ""

    if gate_name == "spec_approved":
        if not (wo_dir / "spec.md").is_file():
            return False, "spec_approved: spec.md not found"
        return True, ""

    if gate_name == "all_tests_pass":
        # Real execution: run TEST-CHECKs from the WO's task ACs (via run_executable_checks).
        # Falls back to file-presence check only when db_path is not provided or no
        # TEST-CHECKs are registered across the WO's tasks.
        if db_path is not None:
            _tasks = _read_wo_tasks(conn, work_order_id)
            from core.work_orders.verify import run_executable_checks

            _ac_results = run_executable_checks(_tasks, db_path)
            _test_checks: list[dict[str, Any]] = []
            for _task_checks in _ac_results.values():
                _test_checks.extend(c for c in _task_checks if c.get("kind") == "TEST-CHECK")
            if _test_checks:
                _failed = [c for c in _test_checks if not c.get("passed")]
                if _failed:
                    _detail = "; ".join(
                        c.get("error") or f"TEST-CHECK {c['expr']!r} failed" for c in _failed[:3]
                    )
                    return False, f"all_tests_pass: {len(_failed)} TEST-CHECK(s) failed — {_detail}"
                return True, ""
            # No TEST-CHECKs registered — fall through to file-presence check below.
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
        content = _artifact_text(work_order_id, wo_dir, "security_scan", db_path)
        if content is None:
            return False, "security_scan: security-scan.md not found"
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

        verdict_raw = _artifact_text(work_order_id, wo_dir, "review_verdict", db_path)
        if verdict_raw is None:
            return False, (
                f"independent_review: review-verdict.json not found. "
                f"Run: py -m interfaces.cli.ds work-order verify {work_order_id}"
            )
        try:
            verdict = _json.loads(verdict_raw)
        except Exception as exc:
            return False, f"independent_review: review-verdict.json is not valid JSON: {exc}"
        if not verdict.get("passed"):
            # Unreviewable verdicts are NOT a certified pass — they indicate no commit
            # evidence was found (WO-REVIEW-TRACEABILITY).  Return a non-blocking failure
            # so close_work_order can decide whether the always-on AC gate compensates.
            # Do NOT hard-block here: close_work_order bypasses this failure when the
            # AC gate passes (unreviewable + passing AC → closes without force).
            if verdict.get("unreviewable"):
                # Always prefix with "independent_review:" so the caller's
                # startswith("independent_review") filter works consistently.
                inner = verdict.get("unreviewable_reason") or (
                    "no commit evidence found; "
                    "review manually or ensure commits carry the WO id / Work-Order: trailer"
                )
                reason = f"independent_review: unreviewable — {inner}"
                return False, reason
            gap_ids = [w.get("work_order_id", "") for w in verdict.get("spawned_work_orders", [])]
            gap_msg = f" Gap WOs: {', '.join(gap_ids)}" if gap_ids else ""
            return False, (
                f"independent_review: review failed — {verdict.get('summary', 'no summary')}.{gap_msg}"
            )
        return True, ""

    return True, ""


def _read_wo_tasks(conn: Any, work_order_id: str) -> list[dict[str, Any]]:
    """Read tasks for a work order from the live connection.

    Returns a list of dicts with at least ``title`` and ``acceptance_criteria`` keys.
    Works whether or not the ``acceptance_criteria`` column exists.
    """
    has_ac = any(
        r[1] == "acceptance_criteria"
        for r in conn.execute("PRAGMA table_info(business_tasks)").fetchall()
    )
    cols = "title, description, status" + (", acceptance_criteria" if has_ac else "")
    rows = conn.execute(
        f"SELECT {cols} FROM business_tasks WHERE work_order_id = ? ORDER BY created_at ASC",
        (work_order_id,),
    ).fetchall()
    return [
        {
            "title": r[0],
            "description": r[1] or "",
            "status": r[2],
            "acceptance_criteria": (r[3] or "") if has_ac else "",
        }
        for r in rows
    ]


def _run_ac_gate(
    conn: Any,
    *,
    work_order_id: str,
    db_path: Path,
) -> list[str]:
    """Run all executable checks across a WO's tasks.  Return list of failure reasons.

    The AC gate is always-on regardless of WO type:
    - If there are NO executable checks at all → returns a single failure reason
      (at least one check is required unless ``force=True``).
    - If any checks fail → returns a failure reason per failing check (up to 5).
    - If all checks pass → returns ``[]``.
    """
    from core.work_orders.verify import run_executable_checks

    tasks = _read_wo_tasks(conn, work_order_id)
    ac_results = run_executable_checks(tasks, db_path)

    # Flatten all check results.
    all_checks: list[dict[str, Any]] = []
    for task_checks in ac_results.values():
        all_checks.extend(task_checks)

    if not all_checks:
        return [
            "executable_ac: no executable checks (SQL-CHECK / TEST-CHECK / API-CHECK) found "
            "across all tasks — at least one is required to close without force=True"
        ]

    failed = [c for c in all_checks if not c.get("passed")]
    if not failed:
        return []

    reasons: list[str] = []
    for c in failed[:5]:
        kind = c.get("kind", "CHECK")
        expr = c.get("expr", "")
        err = c.get("error") or "check returned falsy"
        reasons.append(f"executable_ac: {kind} {expr!r} FAILED — {err}")
    if len(failed) > 5:
        reasons.append(f"executable_ac: …and {len(failed) - 5} more failed check(s)")
    return reasons


def _check_originating_symptom(symptom: str, db_path: Path) -> str | None:
    """Return failure reason if any SQL-CHECK line in symptom still fails, else None.

    Mirrors _run_sql_checks() in verify.py but is a direct blocking check:
    the first failing line returns a reason; if all pass, returns None.
    """
    import sqlite3 as _sqlite3

    try:
        conn = _sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception as exc:
        return f"originating_symptom: could not open DB for symptom check: {exc}"

    try:
        for raw_line in symptom.splitlines():
            line = raw_line.strip()
            if not line.upper().startswith("SQL-CHECK:"):
                continue
            sql = line[len("SQL-CHECK:") :].strip()  # noqa: E203
            try:
                row = conn.execute(sql).fetchone()
                val = row[0] if row is not None else None
                if not val:
                    return (
                        f"originating_symptom: SQL-CHECK still failing —"
                        f" {sql!r} returned {val!r}"
                    )
            except Exception as exc:
                return f"originating_symptom: SQL-CHECK error — {exc}"
    finally:
        conn.close()

    return None


def _lookup_work_order_and_gates(conn: Any, work_order_id: str) -> dict[str, Any]:
    """Internal helper: read WO row + type row, return everything close needs.

    Returns either ``{"ok": False, "error": ...}`` or a dict with keys:
    ``work_order_id, title, wo_status, type_id, project_id, milestone_id,
    pre_gate, post_gate, originating_symptom``.
    """

    wo_row = conn.execute(
        "SELECT work_order_id, title, status, work_order_type, project_id,"
        " milestone_id, originating_symptom"
        " FROM business_work_orders WHERE work_order_id = ?",
        (work_order_id,),
    ).fetchone()
    if wo_row is None:
        return {"ok": False, "error": f"Work order not found: {work_order_id}"}

    wo_id, title, wo_status, wo_type, project_id, milestone_id, orig_symptom = wo_row

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
        "originating_symptom": orig_symptom,
    }


def _evaluate_gates(
    conn: Any,
    *,
    pre_gate: str | None,
    post_gate: str | None,
    work_order_id: str,
    project_id: str,
    planning_root: Path,
    db_path: Path | None = None,
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
            db_path=db_path,
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

        # T1: Task-completeness gate — NOTHING LEFT HANGING. A WO with any task that
        # is not done (or deliberately cancelled) cannot close without force=True.
        # Mirrors mark_task_done's "remaining" predicate (status NOT IN complete|cancelled)
        # so the close view agrees with the count surfaced as each task is completed.
        # This failure is NOT subject to the independent_review bypass below — it always
        # blocks unless forced, and a forced close records it via the gate.bypassed path.
        _incomplete_tasks = conn.execute(
            "SELECT title, status FROM business_tasks"
            " WHERE work_order_id = ? AND status NOT IN ('complete', 'cancelled')"
            " ORDER BY created_at ASC",
            (work_order_id,),
        ).fetchall()
        if _incomplete_tasks:
            _n_incomplete = len(_incomplete_tasks)
            _preview = "; ".join(f"{_t!r} [{_s}]" for _t, _s in _incomplete_tasks[:3])
            _more = f"; …and {_n_incomplete - 3} more" if _n_incomplete > 3 else ""
            gate_failures.append(
                f"tasks_done: {_n_incomplete} task(s) not marked done — {_preview}{_more}"
            )

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
    # (or the registered remediation WOs) so the operator — or the execute-work-orders
    # workflow's next-iteration node — can start it. Close deliberately does NOT
    # auto-start anything: the old auto-start piled up dangling in_progress WOs on
    # every directed close. The autonomous loop now starts the next WO explicitly in
    # its next-iteration node, so nothing depends on this being a side effect.
    if _verify_ran and _verify_result is not None and _project_id_for_autostart:
        if _has_gaps:
            # Report the registered remediation WO(s); do not start them.
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
                    f"Run: py -m interfaces.cli.ds work-order start {gap_wo_id} to begin remediation.\n"
                    f"Main session: review "
                    f".planning/work-orders/{work_order_id}/review-verdict.json for full detail.\n"
                    f"{_sep}\n"
                )
                result["spawned_work_orders"] = spawned
                result["next_command"] = f"ds work-order start {gap_wo_id}"
                result["next_block"] = (
                    f"NEXT WORK ORDER (remediation): {gap_wo_title}"
                    f" / ID: {gap_wo_id}"
                    f" / Run: py -m interfaces.cli.ds work-order start {gap_wo_id}"
                )
        else:
            # Verify passed — advertise the authoritative project-wide ready-set pick
            # (get_next_work_order respects cross-milestone ordering, dependencies, and
            # startability, unlike the naive same-milestone next_wo computed above), but
            # do NOT start it. Starting is an explicit operator / workflow action.
            from core.projects.queries import get_next_work_order as _get_next

            _next_result = _get_next(
                project_id=_project_id_for_autostart,
                source_root=source_root,
                dream_studio_home=dream_studio_home,
            )
            _next_wo = _next_result.get("work_order") if _next_result.get("ok") else None
            if _next_wo:
                _next_id = _next_wo["work_order_id"]
                _next_title = _next_wo["title"]
                result["next_work_order"] = {
                    "work_order_id": _next_id,
                    "title": _next_title,
                    "type": _next_wo.get("type") or _next_wo.get("work_order_type"),
                    "sequence_order": _next_wo.get("sequence_order"),
                    "next_command": f"ds work-order start {_next_id}",
                }
                result["next_command"] = f"ds work-order start {_next_id}"
                result["next_block"] = (
                    f"NEXT WORK ORDER: {_next_title}"
                    f" / ID: {_next_id}"
                    f" / Run: py -m interfaces.cli.ds work-order start {_next_id}"
                )
            else:
                result["next_block"] = "NO NEXT WORK ORDER FOUND / MILESTONE COMPLETE"

    # Flush the work_order.closed spool event through the projection pipeline so
    # callers see status='closed' in the read model without a manual sync_tick.
    # Best-effort — a transient projection failure degrades to the daemon's next cycle.
    try:
        from core.projections.runner import sync_tick as _sync_tick_post

        _sync_tick_post()
    except Exception:
        pass

    return result
