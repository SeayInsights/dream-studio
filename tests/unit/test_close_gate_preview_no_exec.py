"""The close-gate preview has a non-executing mode, and the executing one is unchanged.

`check_close_gates` is documented as non-mutating, which meant only that it leaves the work
order's status alone. Left running, it starts a subprocess per TEST-CHECK, sends an in-process
request per API-CHECK, runs `git log` for provenance staleness, and writes a
`validation.result_recorded` event per executed check. `check_close_gates(run_checks=False)`
does none of that, and says per gate what it therefore could not evaluate.

Three groups, in this order:

1. The default is pinned. Existing callers (the `ds` CLI close path) see exactly what they saw.
2. The non-executing mode reports pass / fail / not_run, and never lets not_run read as pass.
3. The non-executing mode starts no subprocess, makes no request, writes no event and writes
   nothing to the database -- asserted on all four, with controls showing each detector fires
   when the executing mode runs.
"""

from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders.artifact_envelope import wrap
from core.work_orders.artifacts import set_wo_artifact

PROJECT_ID = "abababab-abab-abab-abab-abababababab"
# Created before the change-impact enforcement date, so that gate is grandfathered and the
# scenarios below are about the gates they name.
CREATED = "2020-01-01T00:00:00+00:00"
SHA = "a" * 40

#: A type whose gates exercise every kind of dependence: all_tests_pass (executes),
#: spec_approved (a pure file read that fails), security_scan (pure read + a git staleness
#: comparison). `clean` is the same without the failing gate.
MIXED = ("preview_mixed", "all_tests_pass|spec_approved", "security_scan")
CLEAN = ("preview_clean", "all_tests_pass", "security_scan")

#: One of each kind of criterion: a read, a subprocess, a request.
CRITERIA = (
    "SQL-CHECK: SELECT 1 WHERE 1\n"
    "TEST-CHECK: tests/unit/test_nothing_at_all.py::test_x\n"
    "API-CHECK: GET /api/health -> 200\n"
)


class Forbidden(BaseException):
    """Raised by a spy. A BaseException so that the `except Exception: pass` around the
    event emitter and the TEST-CHECK runner cannot swallow it and turn a call into silence."""


def _db(home: Path) -> Path:
    return home / "state" / "studio.db"


def _seed_wo(db: Path, wo_id: str, wo_type: str, *, criteria: str = CRITERIA) -> None:
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_work_orders (work_order_id, project_id, milestone_id, title,"
        " description, status, work_order_type, created_at, updated_at)"
        " VALUES (?, ?, NULL, 'preview', 'd', 'pushed', ?, ?, ?)",
        (wo_id, PROJECT_ID, wo_type, CREATED, CREATED),
    )
    conn.execute(
        "INSERT INTO business_tasks (task_id, work_order_id, project_id, title, description,"
        " status, created_at, updated_at, acceptance_criteria)"
        " VALUES (?, ?, ?, 'the task', 'd', 'complete', ?, ?, ?)",
        (f"{wo_id}-t1", wo_id, PROJECT_ID, CREATED, CREATED, criteria),
    )
    conn.commit()
    conn.close()
    # A scan artifact carrying a recorded commit: the executing path would compare that
    # commit against the repository with `git log`.
    set_wo_artifact(
        wo_id,
        "security_scan",
        wrap("# scan\nPASSED", generator="t", head_commit_sha=SHA),
        db_path=db,
    )


@pytest.fixture
def home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    db = _db(home)
    db.parent.mkdir(parents=True)
    bootstrap_database(db)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects (project_id, name, description, status, project_path,"
        " created_at, updated_at) VALUES (?, 'P', 'd', 'active', ?, ?, ?)",
        (PROJECT_ID, str(tmp_path), CREATED, CREATED),
    )
    for type_id, pre, post in (MIXED, CLEAN):
        conn.execute(
            "INSERT INTO business_work_order_types (type_id, label, pre_build_gate,"
            " build_executor, post_build_gate) VALUES (?, ?, ?, 'x', ?)",
            (type_id, type_id, pre, post),
        )
    conn.commit()
    conn.close()
    _seed_wo(db, "wo-mixed", MIXED[0])
    _seed_wo(db, "wo-clean", CLEAN[0])
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(home))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(home / "events"))
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db))
    return home


def _preview(home: Path, wo_id: str, **kw):
    from core.work_orders.close_main import check_close_gates

    return check_close_gates(
        work_order_id=wo_id,
        source_root=home.parent,
        dream_studio_home=home,
        planning_root=home.parent / "planning",
        **kw,
    )


def _by_gate(result: dict) -> dict[str, dict]:
    return {g["gate"]: g for g in result["gates"]}


def _spool_files(home: Path) -> list[Path]:
    root = home / "events"
    return sorted(p for p in root.rglob("*") if p.is_file()) if root.exists() else []


# ── 1. the default is pinned ─────────────────────────────────────────────────

#: Every key the executing preview has always returned, and no others.
DEFAULT_KEYS = {
    "ok",
    "work_order_id",
    "title",
    "wo_status",
    "type_id",
    "project_id",
    "milestone_id",
    "pre_gate",
    "post_gate",
    "originating_symptom",
    "gate_failures",
    "gates_pass",
}


def _fake_executor(monkeypatch):
    """Stand in for the executing runner, and count how often the preview calls it."""
    import core.work_orders.verify as verify_mod

    calls: list[list[dict]] = []

    def fake(tasks, db_path, project_root=None):
        calls.append(tasks)
        return {
            "the task": [
                {"kind": "SQL-CHECK", "expr": "SELECT 1 WHERE 1", "passed": True},
                {
                    "kind": "TEST-CHECK",
                    "expr": "tests/unit/test_nothing_at_all.py::test_x",
                    "passed": False,
                    "error": "boom",
                },
            ]
        }

    monkeypatch.setattr(verify_mod, "run_executable_checks", fake)
    stale: list[tuple] = []

    import core.work_orders.artifact_envelope as env_mod

    monkeypatch.setattr(
        env_mod, "wo_commits_after", lambda *a, **k: stale.append(a) or []  # noqa: B023
    )
    return calls, stale


def test_pin_default_preview_still_executes_and_returns_the_old_shape(home, monkeypatch):
    """No `run_checks` argument is the executing preview: the runner is called (once per
    gate that executes), provenance staleness is still compared against git, and the result
    carries exactly the keys it always did -- none of the new ones."""
    calls, stale = _fake_executor(monkeypatch)

    result = _preview(home, "wo-mixed")

    assert set(result) == DEFAULT_KEYS, set(result) ^ DEFAULT_KEYS
    assert result["ok"] is True and result["gates_pass"] is False
    assert result["gate_failures"] == [
        "all_tests_pass: 1 TEST-CHECK(s) failed — boom",
        "spec_approved: spec.md not found",
        "executable_ac: TEST-CHECK 'tests/unit/test_nothing_at_all.py::test_x' FAILED — boom",
    ]
    assert (
        len(calls) == 2
    ), "the executing preview runs the checks for all_tests_pass AND executable_ac"
    assert len(stale) == 1, "the executing preview still compares the scan's commit with git"


def test_pin_run_checks_true_is_the_default(home, monkeypatch):
    """Spelling the default out changes nothing."""
    _fake_executor(monkeypatch)
    assert _preview(home, "wo-mixed", run_checks=True) == _preview(home, "wo-mixed")


def test_pin_default_preview_still_reaches_the_runner(home, monkeypatch):
    """With every execution path spied to raise, the default preview trips one. (The
    per-primitive controls at the end of this file show which, one criterion at a time.)"""
    calls = _spy_everything(monkeypatch)
    with pytest.raises(Forbidden):
        _preview(home, "wo-clean")
    assert calls, "the default preview executed nothing"


# ── 2. pass / fail / not_run ─────────────────────────────────────────────────


def test_the_non_executing_preview_marks_what_it_could_not_run(home):
    result = _preview(home, "wo-clean", run_checks=False)

    assert result["ok"] is True and result["checks_run"] is False
    gates = _by_gate(result)
    # The gates that execute are not_run, each with a reason that says what was not done.
    for name in ("all_tests_pass", "executable_ac", "security_scan"):
        assert gates[name]["status"] == "not_run", (name, gates[name])
        assert gates[name]["failures"] == []
        assert gates[name]["not_run"], f"{name} is not_run but says nothing about why"
    # The pure ones were evaluated and passed.
    for name in ("change_impact_affirmed", "structural_invariants", "phase"):
        assert gates[name]["status"] == "pass", (name, gates[name])
    assert set(gates) == {
        "all_tests_pass",
        "security_scan",
        "executable_ac",
        "change_impact_affirmed",
        "structural_invariants",
        "phase",
    }


def test_not_run_never_reads_as_a_pass(home):
    result = _preview(home, "wo-clean", run_checks=False)
    assert result["overall"] == "not_run"
    assert result["gates_pass"] is False
    assert result["gate_failures"] == [], "a gate that was not run is not a failure either"
    assert sorted(result["gates_not_run"]) == ["all_tests_pass", "executable_ac", "security_scan"]
    # A caller reading only the legacy boolean cannot mistake it for a pass.
    assert not result["gates_pass"]


def test_a_definite_failure_outranks_not_run(home):
    result = _preview(home, "wo-mixed", run_checks=False)
    gates = _by_gate(result)
    assert gates["spec_approved"]["status"] == "fail"
    assert gates["spec_approved"]["failures"] == ["spec_approved: spec.md not found"]
    assert result["overall"] == "fail"
    assert result["gate_failures"] == ["spec_approved: spec.md not found"]
    # ...and the gates that could not be evaluated are still reported as such.
    assert gates["all_tests_pass"]["status"] == "not_run"


def test_the_staleness_comparison_is_what_makes_the_scan_gate_not_run(home):
    """security_scan's own content check (no BLOCKED finding) is a read and was done; only
    the git comparison was not, and the reason names it."""
    gate = _by_gate(_preview(home, "wo-clean", run_checks=False))["security_scan"]
    assert gate["status"] == "not_run"
    assert "git log" in gate["not_run"][0]


def test_a_blocked_scan_is_a_failure_not_not_run(home):
    """What can be read is judged even when something else could not be."""
    set_wo_artifact(
        "wo-clean",
        "security_scan",
        wrap("# scan\nBLOCKED: SQL injection in /login", generator="t", head_commit_sha=SHA),
        db_path=_db(home),
    )
    gate = _by_gate(_preview(home, "wo-clean", run_checks=False))["security_scan"]
    assert gate["status"] == "fail", gate


def test_sql_checks_are_evaluated_and_the_rest_are_listed(home):
    ac = _by_gate(_preview(home, "wo-clean", run_checks=False))["executable_ac"]
    note = ac["not_run"][0]
    assert (
        "1 API-CHECK" in note and "1 TEST-CHECK" in note and "SQL" not in note.split("not run")[0]
    )


def test_a_failing_sql_check_is_a_definite_failure(home):
    conn = sqlite3.connect(str(_db(home)))
    conn.execute(
        "UPDATE business_tasks SET acceptance_criteria = ? WHERE work_order_id = 'wo-clean'",
        ("SQL-CHECK: SELECT 1 WHERE 0\nTEST-CHECK: tests/unit/test_x.py::t\n",),
    )
    conn.commit()
    conn.close()
    ac = _by_gate(_preview(home, "wo-clean", run_checks=False))["executable_ac"]
    assert ac["status"] == "fail"
    assert "SQL-CHECK" in ac["failures"][0] and "FAILED" in ac["failures"][0]
    assert ac["not_run"], "the TEST-CHECK beside it is still reported as not run"


def test_an_unrecognised_check_kind_fails_closed_without_executing(home, monkeypatch):
    conn = sqlite3.connect(str(_db(home)))
    conn.execute(
        "UPDATE business_tasks SET acceptance_criteria = 'FOO-CHECK: whatever'"
        " WHERE work_order_id = 'wo-clean'"
    )
    conn.commit()
    conn.close()
    _spy_everything(monkeypatch)
    ac = _by_gate(_preview(home, "wo-clean", run_checks=False))["executable_ac"]
    assert ac["status"] == "fail" and "Unknown check kind" in ac["failures"][0]


def test_no_registered_test_check_is_a_definite_failure_of_all_tests_pass(home):
    conn = sqlite3.connect(str(_db(home)))
    conn.execute(
        "UPDATE business_tasks SET acceptance_criteria = 'SQL-CHECK: SELECT 1 WHERE 1'"
        " WHERE work_order_id = 'wo-clean'"
    )
    conn.commit()
    conn.close()
    result = _preview(home, "wo-clean", run_checks=False)
    gate = _by_gate(result)["all_tests_pass"]
    assert gate["status"] == "fail" and "UNVERIFIED" in gate["failures"][0]
    # Only SQL-CHECKs were registered, and they were all evaluated: nothing was left unrun.
    assert _by_gate(result)["executable_ac"]["status"] == "pass"


def test_an_unknown_work_order_is_refused(home):
    result = _preview(home, "wo-nope", run_checks=False)
    assert result["ok"] is False and "not found" in result["error"]
    assert "gates" not in result


def test_a_non_executing_evaluation_without_a_not_run_sink_is_refused():
    """`run_gate_check` returns a bare (passed, reason). A not-run gate answering
    `(True, "")` with nowhere to say it was skipped would be indistinguishable from a pass,
    so that combination raises instead of defaulting."""
    from core.work_orders.close_gates import run_gate_check

    with pytest.raises(ValueError, match="not_run"):
        run_gate_check(
            "security_scan",
            planning_root=Path("."),
            work_order_id="x",
            project_id="p",
            conn=None,
            run_checks=False,
        )


# ── 3. no subprocess, no request, no event, no database write ───────────────


def _spy_everything(monkeypatch) -> list[str]:
    """Make every way of leaving the process raise `Forbidden`, and record the attempt.

    Patched at two depths -- the low-level primitive (Popen, TestClient, the spool writers)
    and the runner functions above them -- so that bypassing one layer is still caught by
    the other.
    """
    calls: list[str] = []

    def boom(name):
        def spy(*a, **k):
            calls.append(name)
            raise Forbidden(name)

        return spy

    for attr in ("Popen", "run", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, attr, boom(f"subprocess.{attr}"))
    import os

    monkeypatch.setattr(os, "system", boom("os.system"))

    import starlette.testclient as tc

    monkeypatch.setattr(tc.TestClient, "__init__", boom("TestClient"))
    monkeypatch.setattr(tc.TestClient, "request", boom("TestClient.request"))

    import emitters.shared.spool_writer as sw
    import spool.writer as spool_writer

    monkeypatch.setattr(sw, "write_envelopes", boom("write_envelopes"))
    monkeypatch.setattr(spool_writer, "write_event", boom("write_event"))

    import core.work_orders.verify as verify_mod
    import core.work_orders.verify_executor as vx

    for mod in (vx, verify_mod):
        for fn in (
            "run_executable_checks",
            "_run_one_test_check",
            "_run_one_api_check",
            "_emit_validation_result_event",
        ):
            if hasattr(mod, fn):
                monkeypatch.setattr(mod, fn, boom(f"{mod.__name__}.{fn}"))

    import core.work_orders.artifact_envelope as env_mod

    for fn in ("git_head_sha", "commits_after", "wo_commits_after"):
        monkeypatch.setattr(env_mod, fn, boom(f"artifact_envelope.{fn}"))
    return calls


def test_the_non_executing_preview_starts_no_subprocess_makes_no_request_writes_nothing(
    home, monkeypatch
):
    # A held connection whose data_version changes if ANY other connection commits a write:
    # an independent detector for "nothing was written to the authority", including a schema
    # migration applied by an open.
    watcher = sqlite3.connect(str(_db(home)))
    before_version = watcher.execute("PRAGMA data_version").fetchone()[0]
    before_spool = _spool_files(home)
    calls = _spy_everything(monkeypatch)

    for wo_id in ("wo-mixed", "wo-clean"):
        result = _preview(home, wo_id, run_checks=False)
        assert result["ok"] is True and result["checks_run"] is False

    assert calls == [], f"the non-executing preview reached: {calls}"
    assert _spool_files(home) == before_spool, "an event or file was written to the spool"
    assert (
        watcher.execute("PRAGMA data_version").fetchone()[0] == before_version
    ), "something committed a write to the authority"
    watcher.close()


def test_the_database_write_detector_fires_on_a_write(home):
    """Control for the detector above: it is not simply constant."""
    watcher = sqlite3.connect(str(_db(home)))
    before = watcher.execute("PRAGMA data_version").fetchone()[0]
    other = sqlite3.connect(str(_db(home)))
    other.execute("UPDATE business_work_orders SET title = 'changed'")
    other.commit()
    other.close()
    assert watcher.execute("PRAGMA data_version").fetchone()[0] != before
    watcher.close()


def _spy_primitives_only(monkeypatch) -> list[str]:
    calls: list[str] = []

    def boom(name):
        def spy(*a, **k):
            calls.append(name)
            raise Forbidden(name)

        return spy

    for attr in ("Popen", "run"):
        monkeypatch.setattr(subprocess, attr, boom(f"subprocess.{attr}"))
    return calls


@pytest.mark.parametrize(
    "criteria,expected",
    [
        ("TEST-CHECK: tests/unit/test_x.py::t", "subprocess."),
        ("API-CHECK: GET /api/health", "TestClient"),
        ("SQL-CHECK: SELECT 1 WHERE 1", "write_envelopes"),
    ],
)
def test_each_kind_of_check_trips_its_own_detector_when_executed(
    home, monkeypatch, criteria, expected
):
    """The executing preview, one criterion at a time: a TEST-CHECK starts a subprocess, an
    API-CHECK builds a TestClient, and even a SQL-CHECK emits an event. That last one matters:
    the event is written for EVERY executed check, including the read-only ones, so reading
    the issue's "SQL-CHECK is read-only" as "SQL-CHECK has no side effect" would be wrong."""
    conn = sqlite3.connect(str(_db(home)))
    conn.execute("UPDATE business_tasks SET acceptance_criteria = ?", (criteria,))
    conn.commit()
    conn.close()
    calls = _spy_primitives_only(monkeypatch)
    import emitters.shared.spool_writer as sw
    import starlette.testclient as tc

    def spy(name):
        def f(*a, **k):
            calls.append(name)
            raise Forbidden(name)

        return f

    monkeypatch.setattr(tc.TestClient, "__init__", spy("TestClient"))
    monkeypatch.setattr(sw, "write_envelopes", spy("write_envelopes"))

    with pytest.raises(Forbidden):
        _preview(home, "wo-clean")
    assert any(c.startswith(expected) for c in calls), (criteria, calls)
