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

from .close_shared import _artifact_text, _artifact_with_envelope


def _provenance_staleness(
    envelope: dict[str, Any] | None,
    *,
    work_order_id: str,
    conn: Any,
    db_path: Path | None,
) -> str | None:
    """WO-scoped staleness: WO-attributed commits landed after the artifact's sha.

    Returns a human-readable staleness description, or None when the artifact is
    fresh or staleness cannot be determined (no envelope/sha, no git, unknown sha
    — envelope *presence* is enforced separately by gates that require it).
    """
    if not envelope:
        return None
    sha = envelope.get("head_commit_sha")
    if not sha or db_path is None:
        return None
    from core.work_orders.artifact_envelope import wo_commits_after
    from core.work_orders.verify import resolve_project_root

    title: str | None = None
    try:
        row = conn.execute(
            "SELECT title FROM business_work_orders WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        title = row[0] if row else None
    except Exception:
        pass
    newer = wo_commits_after(
        sha, resolve_project_root(work_order_id, db_path), work_order_id, title=title
    )
    if newer:
        return (
            f"{len(newer)} work-order commit(s) landed after it was produced "
            f"(at {sha[:12]}; newest {newer[0][:12]})"
        )
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
    execute TEST-CHECKs from the WO's task acceptance criteria. Without a db_path
    (or with no TEST-CHECK registered) that gate fails as UNVERIFIED — the legacy
    ``test-results.md`` file-presence fallback was retired by WO-CI-COMPLETENESS,
    since a hand-writable file containing "PASSED" is not evidence.
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
        from core.gates.spec_ratification import evaluate_api_contract

        contract, _contract_env = _artifact_with_envelope(
            work_order_id, wo_dir, "api_contract", db_path
        )
        _stale = _provenance_staleness(
            _contract_env, work_order_id=work_order_id, conn=conn, db_path=db_path
        )
        if _stale:
            return False, (
                f"api_contract_exists: api-contract.md is stale — {_stale}. "
                "Regenerate the contract and re-store the artifact."
            )
        ok, reason = evaluate_api_contract(contract, _wo_created_at(conn, work_order_id))
        return (True, "") if ok else (False, f"api_contract_exists: {reason}")

    if gate_name == "api_contract_and_security_review":
        from core.gates.spec_ratification import evaluate_api_contract

        contract = _artifact_text(work_order_id, wo_dir, "api_contract", db_path)
        ok, reason = evaluate_api_contract(contract, _wo_created_at(conn, work_order_id))
        if not ok:
            return False, f"api_contract_and_security_review: {reason}"
        if _artifact_text(work_order_id, wo_dir, "security_scan", db_path) is None:
            return False, "api_contract_and_security_review: security-scan.md not found"
        return True, ""

    if gate_name == "spec_approved":
        if not (wo_dir / "spec.md").is_file():
            return False, "spec_approved: spec.md not found"
        return True, ""

    if gate_name == "all_tests_pass":
        # Real execution: run TEST-CHECKs from the WO's task ACs (via run_executable_checks).
        # No db_path, or no TEST-CHECK registered across the WO's tasks, means the gate
        # has nothing to execute — it fails as UNVERIFIED below. There is no
        # file-presence fallback (WO-CI-COMPLETENESS retired it).
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
                # MISADDRESSED IS NOT FAILED (WO-VERIFY-GRADES-DELIVERY). A check that
                # could not FIND its target (pytest exit 4/5) says nothing about the
                # work: on 2026-08-19 three TEST-CHECKs reported FAILED for work that
                # was merged and green on three platforms, purely because the working
                # tree was on another branch. Reported as its own state so the
                # operator is told to fix the ADDRESS, not the code — and so this
                # never reads as a false verdict about the work either way.
                _unaddressed = [c for c in _failed if c.get("unaddressed")]
                if _unaddressed and len(_unaddressed) == len(_failed):
                    _detail = "; ".join(
                        f"{c['expr']!r}: {c.get('error') or 'target not found'}"
                        for c in _unaddressed[:3]
                    )
                    return False, (
                        f"all_tests_pass: UNVERIFIED — {len(_unaddressed)} TEST-CHECK(s)"
                        f" could not be RUN (target not found), none actually failed."
                        f" This is not a verdict about the work: verify from the"
                        f" branch/commit where it landed, or repoint the criterion — {_detail}"
                    )
                if _failed:
                    _detail = "; ".join(
                        c.get("error") or f"TEST-CHECK {c['expr']!r} failed" for c in _failed[:3]
                    )
                    _note = (
                        f" ({len(_unaddressed)} of these could not be run at all —"
                        " misaddressed rather than failing)"
                        if _unaddressed
                        else ""
                    )
                    return False, (
                        f"all_tests_pass: {len(_failed)} TEST-CHECK(s) failed{_note} — {_detail}"
                    )
                return True, ""
        # WO-CI-COMPLETENESS: the legacy Path B fallback (test-results.md containing
        # the string "PASSED" — a hand-writable, never-freshness-checked file) is
        # RETIRED. With no executable TEST-CHECKs and no db context this gate is
        # UNVERIFIED and says so explicitly, naming the remediation.
        return False, (
            "all_tests_pass: UNVERIFIED — no TEST-CHECK acceptance criteria are"
            " registered across this WO's tasks (or no db context to execute them)."
            " Register a TEST-CHECK AC (bare pytest node-id or 'cmd: ...') on a task,"
            " or attest a design-only WO via: py -m interfaces.cli.ds work-order attest."
            " The test-results.md string fallback is retired."
        )

    if gate_name == "design_critique":
        import re as _re

        critique_path = wo_dir / "design-critique.md"
        if not critique_path.is_file():
            return False, "design_critique: design-critique.md not found"
        from core.work_orders.artifact_envelope import unwrap as _unwrap

        content, _critique_env = _unwrap(critique_path.read_text(encoding="utf-8"))
        _stale = _provenance_staleness(
            _critique_env, work_order_id=work_order_id, conn=conn, db_path=db_path
        )
        if _stale:
            return False, (
                f"design_critique: design-critique.md is stale — {_stale}. "
                "Re-run website:critique and re-store the artifact."
            )
        if content is None:
            return False, "design_critique: design-critique.md is empty"
        match = _re.search(r"Score:\s*(\d+)/(\d+)", content)
        if not match:
            return False, "design_critique: no 'Score: N/M' found in design-critique.md"
        score = int(match.group(1))
        if score < 3:
            return False, f"design_critique: score {score} is below minimum 3"
        return True, ""

    if gate_name == "security_scan":
        content, _scan_env = _artifact_with_envelope(
            work_order_id, wo_dir, "security_scan", db_path
        )
        if content is None:
            return False, "security_scan: security-scan.md not found"
        # WO-VERIFY-PROVENANCE: enveloped scans must not predate newer WO commits.
        # Legacy (envelope-less) scans keep their historical acceptance.
        _stale = _provenance_staleness(
            _scan_env, work_order_id=work_order_id, conn=conn, db_path=db_path
        )
        if _stale:
            return False, (
                f"security_scan: security-scan.md is stale — {_stale}. "
                "Re-run the security audit and re-store the artifact."
            )
        from core.gates.security_verdict import is_security_blocked

        if is_security_blocked(content):
            return False, "security_scan: security-scan.md reports a BLOCKED finding"
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

        verdict_raw, verdict_envelope = _artifact_with_envelope(
            work_order_id, wo_dir, "review_verdict", db_path
        )
        if verdict_raw is None:
            return False, (
                f"independent_review: review-verdict.json not found. "
                f"Run: py -m interfaces.cli.ds work-order verify {work_order_id}"
            )
        # WO-VERIFY-PROVENANCE: a verdict without a provenance envelope is
        # hand-written or pre-provenance — either way it is not a certified
        # review. The envelope is a tripwire, not a signature: it makes a
        # hand-written verdict detectably different from verify's output. A
        # missing head_commit_sha (project without git) skips only the
        # staleness check — _provenance_staleness handles that case.
        if not verdict_envelope or not verdict_envelope.get("generator"):
            return False, (
                f"independent_review: verdict lacks a provenance envelope "
                f"(hand-written or pre-provenance) — re-run: "
                f"py -m interfaces.cli.ds work-order verify {work_order_id}"
            )
        _stale = _provenance_staleness(
            verdict_envelope, work_order_id=work_order_id, conn=conn, db_path=db_path
        )
        if _stale:
            return False, (
                f"independent_review: verdict is stale — {_stale}. Re-run: "
                f"py -m interfaces.cli.ds work-order verify {work_order_id}"
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


def _wo_created_at(conn: Any, work_order_id: str) -> str | None:
    """Return a work order's ISO created_at, or None if unavailable.

    None → the ratified-contract gate treats the WO as grandfathered (never falsely
    blocks close when the row/column is missing, e.g. in a minimal test DB).
    """
    try:
        row = conn.execute(
            "SELECT created_at FROM business_work_orders WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
    except Exception:
        return None
    return row[0] if row else None


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


def _is_operator_attested(work_order_id: str, db_path: Path) -> bool:
    """True if the WO carries a passing OPERATOR attestation.

    ``ds work-order attest`` records a review verdict with
    ``certification_basis == "operator_attested"`` and ``passed == True`` — an explicit,
    audited human certification. Used to exempt attested design-only WOs (no executable
    check by nature) from the executable_ac force requirement.
    """
    import json as _json

    from core.work_orders.artifacts import get_wo_artifact

    raw = get_wo_artifact(work_order_id, "review_verdict", db_path=db_path)
    if not raw:
        return False
    try:
        verdict = _json.loads(raw)
    except Exception:
        return False
    return bool(verdict.get("passed")) and verdict.get("certification_basis") == "operator_attested"


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
        # Design-only WOs whose deliverable is an operator-local docstore artifact (a spec, an
        # ADR, a capability map) have no code to executably check. An OPERATOR ATTESTATION
        # (ds work-order attest) is the human certification for such work — an explicit, audited
        # action recorded as a passing operator-attested review verdict. When present, it
        # satisfies executable_ac without force. Un-attested zero-check WOs still require a check
        # or force, preserving the no-false-done guard for code work orders.
        if _is_operator_attested(work_order_id, db_path):
            return []
        return [
            "executable_ac: no executable checks (SQL-CHECK / TEST-CHECK / API-CHECK) found "
            "across all tasks — at least one is required to close without force=True "
            "(or attest the WO if its deliverable is operator-local and has no code to check)"
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


def symptom_check_detail(
    symptom: str,
    db_path: Path,
    *,
    work_order_id: str | None = None,
    project_root: Path | None = None,
    title: str | None = None,
) -> list[dict[str, Any]]:
    """Each SQL-CHECK line with its live result — symptom VISIBILITY at close.

    WO-CI-COMPLETENESS: the audit found symptom SQL could be trivially true
    (``SELECT 1 WHERE EXISTS (...business_projects...)``) and was never shown
    to the operator. Close output now carries every check verbatim with its
    result, plus a ``trivially_true`` flag when the SQL has no FROM clause at
    all (nothing real is being asserted).

    Gap WO ade31afb: when the WO's commit diff is collectable, each entry also
    carries ``diff_related`` — whether ANY table the SQL reads appears in the
    diff text. A symptom asserting only tables the change never touched is the
    decorative-symptom pattern the audit flagged. None = undeterminable (no
    git evidence / no tables in the SQL). Advisory — never changes the gate
    outcome; the blocking re-check stays in ``_check_originating_symptom``.
    """
    import re as _re
    import sqlite3 as _sqlite3

    diff_text: str | None = None
    if work_order_id and project_root is not None:
        try:
            from core.work_orders.verify_git import _collect_git_commits

            diff_text = _collect_git_commits(project_root, work_order_id, title=title)
        except Exception:
            diff_text = None

    details: list[dict[str, Any]] = []
    try:
        conn = _sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception:
        return details
    try:
        for raw_line in symptom.splitlines():
            line = raw_line.strip()
            if not line.upper().startswith("SQL-CHECK:"):
                continue
            sql = line[len("SQL-CHECK:") :].strip()  # noqa: E203
            tables = sorted(
                set(
                    _re.findall(
                        r"\b(?:FROM|JOIN|INTO|UPDATE)\s+([A-Za-z_][A-Za-z0-9_]*)",
                        sql,
                        _re.IGNORECASE,
                    )
                )
            )
            # Word-boundary match (gap WO 681b294e): a naive substring test made
            # table `things` match `somethings`, a filename, or a comment —
            # inflating diff-relatedness into a false reassurance.
            entry: dict[str, Any] = {
                "sql": sql,
                "tables": tables,
                "trivially_true": not tables,
                "diff_related": (
                    any(_re.search(r"\b" + _re.escape(t) + r"\b", diff_text) for t in tables)
                    if (diff_text and tables)
                    else None
                ),
            }
            try:
                row = conn.execute(sql).fetchone()
                entry["value"] = row[0] if row is not None else None
                entry["passed"] = bool(entry["value"])
            except Exception as exc:
                entry["value"] = None
                entry["passed"] = False
                entry["error"] = str(exc)
            details.append(entry)
    finally:
        conn.close()
    return details


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
