"""WO-VERIFY-GRADES-DELIVERY: a check that cannot find its target is not a failure.

On 2026-08-19, closing a work order whose fix was merged and green on all three
platforms reported three TEST-CHECKs as FAILED — because the working tree was on
an unrelated branch and pytest exited 4 ("usage error / file not found"), which
the gate rendered identically to exit 1 ("assertions failed").

That misreport sent a real diagnosis down the wrong path: it looked like the
delivered work was broken, and the first written-up root cause was wrong as a
result. A gate whose "the work failed" and "I was pointed at the wrong place" are
the same string cannot be reasoned from — and the pressure it creates is toward
`--force`, which is how false-done gets normalised.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders.verify_executor import (
    _PYTEST_EXIT_MEANING,
    _run_one_test_check,
    _test_check_failure_reason,
)

# ── Exit-code semantics ─────────────────────────────────────────────────────────


def test_pytest_exit_codes_are_distinguished():
    """4 and 5 mean the check never reached the work; 1 means the work is wrong."""
    could_not_run = _test_check_failure_reason(4, is_pytest=True)
    assert "could not run" in could_not_run
    assert "NOT a test failure" in could_not_run

    no_tests = _test_check_failure_reason(5, is_pytest=True)
    assert "NO TESTS COLLECTED" in no_tests
    assert "NOT a test failure" in no_tests

    genuinely_failed = _test_check_failure_reason(1, is_pytest=True)
    assert "FAILED" in genuinely_failed
    assert "NOT a test failure" not in genuinely_failed, (
        "exit 1 IS a test failure — muddying this direction would be the same defect "
        "pointing the other way"
    )


def test_a_cmd_check_is_not_given_pytest_semantics():
    """`cmd:` runs an arbitrary command whose exit codes are its own — 5 from
    `npm test` or `go test` does not mean 'no tests collected'."""
    reason = _test_check_failure_reason(5, is_pytest=False)
    assert "NO TESTS COLLECTED" not in reason
    assert "exited with code 5" in reason


def test_every_documented_pytest_code_has_a_meaning():
    """An unmapped code must still produce a usable message, not a bare number
    dressed up as an explanation."""
    for code in (1, 2, 3, 4, 5):
        assert _PYTEST_EXIT_MEANING[code]
    assert "99" in _test_check_failure_reason(99, is_pytest=True)


# ── The real subprocess, not a mocked exit code ────────────────────────────────


def test_a_nonexistent_node_id_is_reported_as_unaddressed(tmp_path):
    """Driven through the real pytest invocation: the value of this fix is that a
    missing target is *recognised*, and a mocked returncode would only prove the
    branching."""
    check = _run_one_test_check("tests/unit/test_does_not_exist_xyz.py::test_nope", tmp_path)
    assert check["passed"] is False
    assert check["unaddressed"] is True, f"expected a misaddressed verdict: {check}"
    assert check["exit_code"] in (4, 5)
    assert "NOT a test failure" in (check["error"] or "")


def test_a_genuinely_failing_test_is_not_marked_unaddressed(tmp_path):
    """The converse, so `unaddressed` keeps meaning something."""
    failing = tmp_path / "test_real_failure.py"
    failing.write_text("def test_x():\n    assert False\n", encoding="utf-8")
    check = _run_one_test_check(f"{failing.name}::test_x", tmp_path)
    assert check["passed"] is False
    assert check["unaddressed"] is False, "a real assertion failure is about the WORK"
    assert check["exit_code"] == 1


def test_a_passing_test_reports_no_error(tmp_path):
    passing = tmp_path / "test_real_pass.py"
    passing.write_text("def test_x():\n    assert True\n", encoding="utf-8")
    check = _run_one_test_check(f"{passing.name}::test_x", tmp_path)
    assert check["passed"] is True
    assert check["exit_code"] == 0
    assert not check["error"]


# ── The gate's report ──────────────────────────────────────────────────────────


def _wo_with_check(db: Path, expr: str) -> str:
    project_id, wo_id = str(uuid.uuid4()), str(uuid.uuid4())
    now = "2026-08-20T00:00:00+00:00"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (project_id, "P", "", "active", now, now),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, work_order_type,"
        "  status, created_at, updated_at) VALUES (?,?,NULL,'WO','d','cleanup','in_progress',?,?)",
        (wo_id, project_id, now, now),
    )
    conn.execute(
        "INSERT INTO business_tasks"
        " (task_id, work_order_id, project_id, title, description, status, created_at,"
        "  updated_at, acceptance_criteria) VALUES (?,?,?,'t','d','complete',?,?,?)",
        (str(uuid.uuid4()), wo_id, project_id, now, now, f"TEST-CHECK: {expr}"),
    )
    conn.commit()
    conn.close()
    return wo_id


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "state" / "studio.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(path)
    return path


def test_gate_reports_unverified_not_failed_when_no_check_could_run(db, tmp_path):
    """The exact 2026-08-19 shape: every check misaddressed, nothing actually
    failed. The gate must not claim the work failed."""
    from core.work_orders.close_gates import run_gate_check

    wo_id = _wo_with_check(db, "tests/unit/test_absent_target_xyz.py::test_nope")
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    passed, reason = run_gate_check(
        "all_tests_pass",
        planning_root=tmp_path,
        work_order_id=wo_id,
        project_id="",
        conn=conn,
        db_path=db,
    )
    conn.close()

    assert passed is False, "an unrunnable check is not a pass either — no false green"
    assert "UNVERIFIED" in reason
    assert "could not be RUN" in reason
    assert "none actually failed" in reason
    assert "not a verdict about the work" in reason


def test_gate_still_fails_plainly_when_a_check_really_fails(db, tmp_path):
    """`unaddressed` must not become a way for a real failure to read as
    'inconclusive' — that would be the defect inverted, and far worse.

    Uses a ``cmd:`` check that genuinely exits non-zero. The first attempt here
    wrote a failing pytest file into tmp_path and asserted the gate reported a
    failure — and it reported "could not be RUN" instead, CORRECTLY: the gate
    resolves its own project_root and ran pytest from the DS repo, where that
    tmp file does not exist. The gate was right and the test was wrong, which is
    task 1 of this WO (checkout-dependent evaluation) demonstrating itself while
    task 2 was being tested.
    """
    from core.work_orders.close_gates import run_gate_check

    # git is present (this is a git repo) and exits non-zero on an unknown ref.
    wo_id = _wo_with_check(db, "cmd: git rev-parse --verify definitely-not-a-real-ref")

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    passed, reason = run_gate_check(
        "all_tests_pass",
        planning_root=tmp_path,
        work_order_id=wo_id,
        project_id="",
        conn=conn,
        db_path=db,
    )
    conn.close()

    assert passed is False
    assert "TEST-CHECK(s) failed" in reason
    assert "exited with code" in reason
    assert "could not be RUN" not in reason, (
        "a genuine non-zero exit from a cmd: check is a real failure, not a "
        "misaddressed one — softening it would invert the defect"
    )
    assert "UNVERIFIED" not in reason, "a real failure must not be softened to inconclusive"
