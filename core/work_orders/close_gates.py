"""Gate-check predicates for work-order close.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/close.py``. Holds the
per-gate predicate (``run_gate_check``), the always-on executable-AC gate
(``_run_ac_gate``), the originating-symptom regression check, the task-read
helper, the pre/post gate evaluator, and the tasks-done completeness gate
(``_check_tasks_done`` — a NEW function whose body is extracted verbatim from
``close_work_order``'s former inline block). No logic changes otherwise —
extracted verbatim from the original module.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .close_shared import _artifact_text


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
            from core.work_orders.verify import resolve_project_root, run_executable_checks

            _proot = resolve_project_root(work_order_id, db_path)
            _ac_results = run_executable_checks(_tasks, db_path, project_root=_proot)
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
    from core.work_orders.verify import resolve_project_root, run_executable_checks

    tasks = _read_wo_tasks(conn, work_order_id)
    ac_results = run_executable_checks(
        tasks, db_path, project_root=resolve_project_root(work_order_id, db_path)
    )

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


def _check_tasks_done(conn: Any, work_order_id: str) -> list[str]:
    """T1: Task-completeness gate — NOTHING LEFT HANGING. A WO with any task that
    is not done (or deliberately cancelled) cannot close without force=True.
    Mirrors mark_task_done's "remaining" predicate (status NOT IN complete|cancelled)
    so the close view agrees with the count surfaced as each task is completed.
    This failure is NOT subject to the independent_review bypass below — it always
    blocks unless forced, and a forced close records it via the gate.bypassed path.
    """
    failures: list[str] = []
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
        failures.append(f"tasks_done: {_n_incomplete} task(s) not marked done — {_preview}{_more}")
    return failures
