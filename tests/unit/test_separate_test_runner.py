"""WO-SEPARATE-TEST-RUNNER: the substrate enforces who may certify a test result.

Operator directive 2026-08-20: "test and evals should always be ran by a separate
agent. never by the same one that did the work." Then the correction that shaped
this work order: "the dream studio substrate should enforce the ruling ... anything
that is taken as a directive and added locally will fail when someone else deploys
dream studio. dream studio should work out of the box for every user."

So none of this may live in operator-local state. Every mechanism here ships in the
repo — `canonical/` (which projects to every install), the gates, the engine — and
`test_enforcement_needs_no_operator_local_state` is the assertion that keeps it
that way.

THE EVIDENCE IS FROM THE SAME DAY AND IT IS MINE. WO-VERDICT-PARTIAL-WRITE task 3
made `independent_review` report UNREVIEWABLE for any verdict with `passed=False`
and no top-level `summary` / `failure_reasons`. Real verdicts carry NEITHER key:
the prose is under `completion.summary`, the findings under `gaps` /
`spawned_work_orders`. Every genuinely failing verdict would have been softened to
"incomplete record — re-run verify", hiding real gaps behind a retry prompt.
Fourteen of my own tests passed, because they asserted a verdict shape I invented
rather than one read from disk.

A green suite run by its author is agreement, not evidence.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.gates.merge_readiness import merge_readiness
from core.work_orders.close_gates import run_gate_check
from core.work_orders.verify_executor import _run_one_test_check, record_test_execution

_REPO = Path(__file__).resolve().parents[2]
_CANONICAL = _REPO / "canonical" / "skills"
_PROJECTED = _REPO / "dist" / "plugin" / "skills"

# Commands chosen for portability across the three CI platforms: git is present on
# all of them, `--version` needs no repository, and an unknown long option is a
# non-zero exit on every git build.
_PASSING_CMD = "cmd: git --version"
_FAILING_CMD = "cmd: git --no-such-flag-here"
_PASSING_AC = f"TEST-CHECK: {_PASSING_CMD}"
_FAILING_AC = f"TEST-CHECK: {_FAILING_CMD}"


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "state" / "studio.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(path)
    return path


def _wo_with_acs(db: Path, acceptance_criteria: list[str | None]) -> str:
    """A work order whose tasks carry the given acceptance criteria, one per task."""
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
        "  status, created_at, updated_at)"
        " VALUES (?,?,NULL,'WO','d','infrastructure','in_progress',?,?)",
        (wo_id, project_id, now, now),
    )
    for index, ac in enumerate(acceptance_criteria):
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, description, status,"
            "  created_at, updated_at, acceptance_criteria)"
            " VALUES (?,?,?,?,?,'complete',?,?,?)",
            (str(uuid.uuid4()), wo_id, project_id, f"task {index}", "", now, now, ac),
        )
    conn.commit()
    conn.close()
    return wo_id


def _gate(name: str, db: Path, planning: Path, wo_id: str) -> tuple[bool, str]:
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        return run_gate_check(
            name, planning_root=planning, work_order_id=wo_id, project_id="", conn=conn, db_path=db
        )
    finally:
        conn.close()


# ── Task 1: the gate EXECUTES, it does not read a report ──────────────────────


def test_the_gate_executes_checks_rather_than_trusting_a_report(db, tmp_path):
    """The invariant that already holds, and which nothing pinned.

    `all_tests_pass` runs each TEST-CHECK in a subprocess at close time. A stored
    artifact claiming success must not be able to talk it out of the result: here a
    `test_results` artifact says PASSED while the registered check genuinely fails,
    and the gate reports the failure.
    """
    from core.work_orders.artifacts import set_wo_artifact

    wo_id = _wo_with_acs(db, [_FAILING_AC])
    set_wo_artifact(
        wo_id,
        "report",
        "# Test results\n\nAll tests PASSED. 5386 passed, 0 failed.\n",
        db_path=db,
        generator="ds work-order build",
        project_root=Path("."),
    )

    passed, reason = _gate("all_tests_pass", db, tmp_path, wo_id)
    assert passed is False, "a self-reported PASSED artifact must not override execution"
    assert "TEST-CHECK" in reason
    assert "PASSED" not in reason, "the gate must not be quoting the author's own claim back"


def test_a_self_reported_pass_does_not_satisfy_the_gate(db, tmp_path):
    """With no executable check registered, a report is all there is — and a report
    is hand-writable, so the gate is UNVERIFIED rather than green.

    This is the retired WO-CI-COMPLETENESS fallback: `test-results.md` containing
    the string "PASSED" used to pass this gate. Pinned because the failure mode is
    silent — re-adding the fallback would make every design-only WO close green.
    """
    from core.work_orders.artifacts import set_wo_artifact

    wo_id = _wo_with_acs(db, [None])
    set_wo_artifact(
        wo_id,
        "report",
        "PASSED — everything is green, honestly.\n",
        db_path=db,
        generator="ds work-order build",
        project_root=Path("."),
    )

    passed, reason = _gate("all_tests_pass", db, tmp_path, wo_id)
    assert passed is False
    assert "UNVERIFIED" in reason
    assert "no TEST-CHECK" in reason
    assert "attest" in reason, "the honest route for a design-only WO must be named"


def test_a_registered_check_that_runs_and_passes_satisfies_the_gate(db, tmp_path):
    """The converse, so "executes" cannot be satisfied by a gate that always fails."""
    wo_id = _wo_with_acs(db, [_PASSING_AC])
    passed, reason = _gate("all_tests_pass", db, tmp_path, wo_id)
    assert passed is True, f"an executed, passing check must satisfy the gate: {reason}"


# ── Task 2: every check result records whether it was executed ─────────────────


def test_check_results_record_whether_they_were_executed():
    """A grader on 2026-08-20 reported honestly that "running pytest was denied by
    the sandbox, so the tests are not confirmed green by execution". That fact lived
    only in prose, so downstream a result backed by a run and one backed by a read
    were indistinguishable. Now every result carries it, on both paths."""
    ran = _run_one_test_check(_PASSING_CMD)
    assert ran["executed"] is True
    assert ran["passed"] is True
    assert ran["exit_code"] == 0

    failed = _run_one_test_check(_FAILING_CMD)
    assert failed["executed"] is True, "a command that ran and failed still RAN"
    assert failed["passed"] is False

    absent = _run_one_test_check("cmd: ds-no-such-binary-a1b2c3")
    assert absent["executed"] is False, "a command that never started did not execute"
    assert absent["not_executed_reason"], "and it must say why"
    assert absent["passed"] is False


def test_an_unparseable_check_is_not_recorded_as_executed():
    """The early-return paths are the easy ones to miss — a result dict that skips
    the subprocess entirely must still carry `executed=False`, or the key is only
    ever True and means nothing."""
    broken = _run_one_test_check('cmd: pytest "unclosed')
    assert broken["executed"] is False
    assert broken["passed"] is False
    assert "unparseable" in (broken["error"] or "")


def test_the_verdict_records_what_its_certification_rests_on():
    """`test_execution_record` reads the acceptance criteria, so it is honest even on
    the verify path that never runs the checks — the distinction that matters is
    "did anything execute", not "could it have"."""
    none_registered = record_test_execution([{"title": "t", "acceptance_criteria": "SQL-CHECK: 1"}])
    assert none_registered["basis"] == "none_registered"
    assert none_registered["registered"] == 0

    tasks = [{"title": "t", "acceptance_criteria": "TEST-CHECK: tests/unit/test_x.py::test_y"}]
    not_run = record_test_execution(tasks)
    assert not_run["basis"] == "not_run_at_verify", "registered but nothing ran"
    assert not_run["registered"] == 1
    assert not_run["executed"] == 0

    executed = record_test_execution(
        tasks,
        {"t": [{"kind": "TEST-CHECK", "executed": True, "passed": True}]},
    )
    assert executed["basis"] == "executed"
    assert executed["passed"] == 1

    # A check that did NOT execute must not be counted as one that did — otherwise
    # a sandboxed grader's verdict reads as execution-backed.
    denied = record_test_execution(
        tasks,
        {"t": [{"kind": "TEST-CHECK", "executed": False, "not_executed_reason": "sandbox"}]},
    )
    assert denied["basis"] == "not_run_at_verify"
    assert denied["executed"] == 0


# ── Task 3: a verdict resting on reading is labelled where it is consumed ──────


def _store_verdict(db: Path, wo_id: str, verdict: dict) -> None:
    from core.work_orders.artifacts import set_wo_artifact

    set_wo_artifact(
        wo_id,
        "review_verdict",
        json.dumps(verdict),
        db_path=db,
        generator="ds work-order verify",
        project_root=Path("."),
    )


def test_a_read_only_verdict_is_labelled_as_such(db):
    """Merge consults the verdict; close executes the checks afterwards. So merge is
    the last point at which "certified by reading" versus "certified by running" can
    change a decision, and it has to be said there."""
    wo_id = _wo_with_acs(db, [None])
    _store_verdict(
        db,
        wo_id,
        {
            "passed": True,
            "completion": {"summary": "the change is correct as read"},
            "test_execution": {
                "registered": 0,
                "executed": 0,
                "passed": 0,
                "basis": "none_registered",
            },
        },
    )
    out = merge_readiness(work_order_id=wo_id, db_path=db)
    assert out["state"] == "passed", "the caveat must not be smuggled in as a failure"
    assert out["ready"] is True
    assert "CAVEAT" in out["advice"]
    assert "not by running it" in out["advice"]
    assert out["execution"]["basis"] == "none_registered"


def test_a_registered_but_unrun_verdict_says_how_many_checks_were_skipped(db):
    wo_id = _wo_with_acs(db, [None])
    _store_verdict(
        db,
        wo_id,
        {
            "passed": True,
            "test_execution": {
                "registered": 3,
                "executed": 0,
                "passed": 0,
                "basis": "not_run_at_verify",
            },
        },
    )
    advice = merge_readiness(work_order_id=wo_id, db_path=db)["advice"]
    assert "CAVEAT" in advice
    assert "3 TEST-CHECK" in advice, "name the count, or the reader cannot judge the gap"


def test_an_execution_backed_verdict_carries_no_caveat(db):
    """The converse. A caveat on every verdict is a caveat nobody reads."""
    wo_id = _wo_with_acs(db, [None])
    _store_verdict(
        db,
        wo_id,
        {
            "passed": True,
            "test_execution": {"registered": 2, "executed": 2, "passed": 2, "basis": "executed"},
        },
    )
    out = merge_readiness(work_order_id=wo_id, db_path=db)
    assert out["state"] == "passed"
    assert "CAVEAT" not in out["advice"]


def test_a_verdict_from_before_this_field_existed_still_reads(db):
    """Every verdict stored before today lacks `test_execution`. Absent must mean
    "unknown", never a caveat asserted about a verdict that cannot answer."""
    wo_id = _wo_with_acs(db, [None])
    _store_verdict(db, wo_id, {"passed": True, "completion": {"summary": "older run"}})
    out = merge_readiness(work_order_id=wo_id, db_path=db)
    assert out["state"] == "passed"
    assert out["execution"] is None
    assert "CAVEAT" not in out["advice"]


def _flat(text: str) -> str:
    """Skill text lowercased with all whitespace collapsed.

    Markdown wraps prose at ~80 columns, so a phrase in the guidance is routinely
    split across a newline. A raw substring check therefore asserts the LINE BREAKS
    as much as the words, and fails on text that says exactly the right thing —
    which is what happened to "derive it from a real stored one".
    """
    import re

    return re.sub(r"\s+", " ", text.lower())


# ── Gap e3a17189: the same fact at close and on resume, not only at merge ──────


def test_the_caveat_is_silent_where_the_checks_have_just_run():
    """`not_run_at_verify` is the ORDINARY state on the git-diff verify path, and
    close executes every registered TEST-CHECK before it can complete. Printing the
    caveat there would put it on nearly every close — and a caveat on everything is
    a caveat nobody reads, which is the failure mode this milestone keeps finding."""
    from core.gates.merge_readiness import execution_caveat

    registered_unrun = {"registered": 2, "executed": 0, "passed": 0, "basis": "not_run_at_verify"}
    assert execution_caveat(registered_unrun) is not None, "merge has not run them yet"
    assert execution_caveat(registered_unrun, checks_ran_here=True) is None

    # "No check exists" is NOT resolved by a caller that runs checks — there was
    # nothing to run. This one speaks in both places.
    none_registered = {"registered": 0, "executed": 0, "passed": 0, "basis": "none_registered"}
    assert execution_caveat(none_registered, checks_ran_here=True) is not None

    assert execution_caveat({"basis": "executed", "registered": 1}) is None
    assert execution_caveat(None) is None, "absent means unknown, never an assertion"


def test_close_surfaces_a_verdict_that_nothing_executed(db, tmp_path):
    """The gap the independent review found: the distinction existed at merge-check
    and nowhere else, so a WO could CLOSE — the moment work is declared done — with
    a review that never ran a test, reading as ordinary certification.

    Drives the real ``close_work_order``. ``force=True`` because the gates are not
    what is under test here (the advisory is), and ``none_registered`` is the basis
    that speaks in every context: there was no check to run, so no caller can have
    run one.
    """
    from unittest.mock import MagicMock, patch

    from core.work_orders.close import close_work_order

    wo_id = _wo_with_acs(db, [None])
    _store_verdict(
        db,
        wo_id,
        {
            "passed": True,
            "completion": {"summary": "read the code"},
            "test_execution": {
                "registered": 0,
                "executed": 0,
                "passed": 0,
                "basis": "none_registered",
            },
        },
    )
    fake_paths = MagicMock()
    fake_paths.sqlite_path = db
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        result = close_work_order(
            work_order_id=wo_id,
            force=True,
            source_root=tmp_path,
            dream_studio_home=tmp_path,
            planning_root=tmp_path / "planning",
        )
    assert result["ok"] is True, f"the caveat must not block the close: {result}"
    warning = result.get("test_execution_warning")
    assert warning, f"close must state what the review rested on: {result}"
    assert "not by running it" in warning


def test_project_state_surfaces_it_where_an_agent_orients(db, tmp_path):
    """Resume is where an agent decides what state the work is in. Same silence
    removal as the unverified-risk ledger and the main-CI advisory beside it."""
    from core.gates.merge_readiness import work_order_execution_caveat

    wo_id = _wo_with_acs(db, [None])
    _store_verdict(
        db,
        wo_id,
        {
            "passed": True,
            "test_execution": {
                "registered": 0,
                "executed": 0,
                "passed": 0,
                "basis": "none_registered",
            },
        },
    )
    caveat = work_order_execution_caveat(wo_id, db_path=db)
    assert caveat and "no TEST-CHECK" in caveat

    # And project state actually reads it — the wiring, not just the reader. A
    # grep is the honest check here: seeding a full active project + milestone to
    # drive get_project_state would test the seeding, not the wiring.
    queries = (_REPO / "core" / "projects" / "queries.py").read_text(encoding="utf-8")
    assert "work_order_execution_caveat" in queries
    assert '"test_execution_warning"' in queries


# ── Task 4: the rule ships in canonical skill text ────────────────────────────

# (canonical pack dir, projected pack dir, mode). The projection renames the pack:
# canonical/skills/core -> dist/plugin/skills/ds-core, which is exactly the kind of
# detail that makes a parity test silently assert nothing if it is guessed.
_RULE_BEARING_MODES = [
    ("core", "ds-core", "build"),
    ("core", "ds-core", "verify"),
    ("ds-workorder", "ds-workorder", "execute"),
    ("ds-workorder", "ds-workorder", "close"),
]


@pytest.mark.parametrize(("pack", "_projected", "mode"), _RULE_BEARING_MODES)
def test_skill_texts_require_a_separate_test_runner(pack: str, _projected: str, mode: str):
    """A rule an agent never reads is not enforcement. These four modes are where an
    agent decides a task is done, decides a WO is verified, and decides to close."""
    path = _CANONICAL / pack / "modes" / mode / "SKILL.md"
    assert path.is_file(), f"missing {path}"
    text = _flat(path.read_text(encoding="utf-8"))
    assert "node id" in text, f"{mode}: the runner must be handed node ids"
    assert (
        "not run its own suite" in text
        or "does not run its own suite" in text
        or "not run its suite" in text
        or "other than the author" in text
        or "spawn a runner" in text
    ), f"{mode}: the rule itself must be stated, not implied"


def test_the_rule_states_its_reason():
    """A rule without its reason gets optimised away by the next agent that is in a
    hurry. The build mode carries the argument and the measurement."""
    text = _flat((_CANONICAL / "core" / "modes" / "build" / "SKILL.md").read_text(encoding="utf-8"))
    assert "agreement, not proof" in text or "agreement, not evidence" in text
    assert "fourteen" in text, "the measured case is the reason — keep it concrete"


@pytest.mark.parametrize(("pack", "projected_pack", "mode"), _RULE_BEARING_MODES)
def test_the_projection_carries_the_rule(pack: str, projected_pack: str, mode: str):
    """dist/plugin is what a plugin install actually reads. A rule that exists only
    in canonical/ is a rule no plugin user is bound by — the same
    two-copies-one-stale shape as the pre-push manifest drift."""
    projected = _PROJECTED / projected_pack / "modes" / mode / "SKILL.md"
    canonical = _CANONICAL / pack / "modes" / mode / "SKILL.md"
    assert projected.is_file(), f"projected SKILL.md missing at {projected}"
    assert projected.read_text(encoding="utf-8").replace("\r\n", "\n") == canonical.read_text(
        encoding="utf-8"
    ).replace("\r\n", "\n"), (
        f"dist/plugin {pack}/{mode} SKILL.md is stale — rebuild it with "
        "integrations.marketplace.plugin_dist.build_plugin_dist"
    )


# ── Task 5: fixtures for stored artifacts come from stored artifacts ──────────


def test_artifact_fixtures_are_documented_as_real():
    """The concrete failure was an invented verdict shape passing fourteen tests.

    Two halves: the rule ships where an agent building tests will read it, and the
    existing real-derived fixture stays labelled as real so it can be copied rather
    than re-invented.
    """
    lowered = _flat(
        (_CANONICAL / "core" / "modes" / "build" / "SKILL.md").read_text(encoding="utf-8")
    )
    assert "durable artifact" in lowered
    assert "derive it from a real" in lowered or "derived from a real" in lowered
    assert "review verdict" in lowered, "name the artifacts this applies to"

    fixture_file = _REPO / "tests" / "unit" / "test_merge_readiness.py"
    text = fixture_file.read_text(encoding="utf-8")
    assert "_REAL_FAILED_VERDICT" in text
    marker = text.split("_REAL_FAILED_VERDICT")[0]
    assert (
        "Copied from an actual stored review-verdict.json" in marker
    ), "the fixture must say where it came from, or the next reader cannot trust it"


# ── Task 6: none of this depends on operator-local state ──────────────────────

_MECHANISM_FILES = [
    "core/work_orders/verify_executor.py",
    "core/work_orders/verify_main.py",
    "core/gates/merge_readiness.py",
    "core/work_orders/close_gates.py",
    "canonical/skills/core/modes/build/SKILL.md",
    "canonical/skills/core/modes/verify/SKILL.md",
    "canonical/skills/ds-workorder/modes/execute/SKILL.md",
    "canonical/skills/ds-workorder/modes/close/SKILL.md",
]


def test_enforcement_needs_no_operator_local_state():
    """The directive's whole point: DS must work out of the box for every user.

    A rule kept in `~/.claude`, in agent memory, or behind a per-operator env var
    binds exactly one operator and silently does nothing on anyone else's install —
    which is the failure mode being corrected here, not a lesser version of it. So
    every mechanism must be a tracked repo file.
    """
    tracked = subprocess.run(
        [
            "git",
            "-C",
            str(_REPO),
            "ls-files",
            "--error-unmatch",
            *_MECHANISM_FILES,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert (
        tracked.returncode == 0
    ), "every mechanism must be a tracked repo file, not local state: " + (tracked.stderr or "")
    listed = {line.strip().replace("\\", "/") for line in (tracked.stdout or "").splitlines()}
    for path in _MECHANISM_FILES:
        assert path in listed, f"{path} is not tracked — it would not ship to another install"


def _env_without_operator_state() -> dict[str, str]:
    """A real environment with every operator-local knob removed.

    Not an empty env: clearing PATH/SYSTEMROOT can fail Python startup for reasons
    that have nothing to do with the claim, which would make this test pass for the
    wrong reason. What matters is that no DS home, adapter config, or per-operator
    override is present.
    """
    import os

    dropped = ("DS_", "DREAM_STUDIO", "CLAUDE")
    return {
        key: value
        for key, value in os.environ.items()
        if not any(key.upper().startswith(prefix) for prefix in dropped)
    }


def test_the_engine_half_imports_with_no_local_configuration():
    """Import and drive the mechanism in a subprocess with no DS home, no adapter
    config and no operator env vars set. A mechanism that needs local setup to
    function is local state wearing a repo file's name."""
    script = (
        "from core.work_orders.verify_executor import record_test_execution;"
        "r = record_test_execution([{'title':'t','acceptance_criteria':'TEST-CHECK: a::b'}]);"
        "assert r['basis'] == 'not_run_at_verify', r;"
        "print('ok')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_env_without_operator_state(),
        timeout=120,
    )
    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert "ok" in proc.stdout
