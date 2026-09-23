"""The watcher: what happens to a work order after its work reaches `main`.

Merge authorisation is pr-smoke, which is a subset. The suite that runs everything is Full
CI on `main`, and it runs AFTER the merge -- so the branch carrying a failure is the one
nobody is watching. Three times in one day a merge put main red and the work was declared
done anyway, because noticing required someone to go and look.
"""

from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest

from core.health.main_ci_watch import (
    MAX_NAMED_FAILURES,
    failing_node_ids,
    remediation_task,
    work_orders_awaiting_ci,
)

# ── reading the failures out of a run ────────────────────────────────────────


def _log(text: str):
    proc = type("P", (), {"returncode": 0, "stdout": text, "stderr": ""})()
    return patch("subprocess.run", return_value=proc)


def test_it_reads_integration_failures_too():
    """The miss that produced a wrong number for an operator.

    Grepping `tests/unit/` once reported 11 failures when there were 16, dropping every
    integration one -- and the wrong count was then repeated out loud. The pattern matches
    `tests/`, so an integration failure is a failure.
    """
    log = (
        "full-ci\tRun\t2026-09-23T00:00:00Z FAILED tests/unit/test_a.py::test_one - AssertionError\n"
        "full-ci\tRun\t2026-09-23T00:00:01Z FAILED tests/integration/test_b.py::test_two\n"
    )
    with _log(log):
        nodes = failing_node_ids("123")
    assert nodes == ["tests/unit/test_a.py::test_one", "tests/integration/test_b.py::test_two"]


def test_the_reason_suffix_is_stripped_from_the_node_id():
    """pytest appends ` - <reason>`; a node id carrying it is not a node id anything can
    run, and it would land in an acceptance criterion that close then fails to execute."""
    with _log("FAILED tests/unit/test_a.py::test_one - AssertionError: assert 0 == 1\n"):
        assert failing_node_ids("1") == ["tests/unit/test_a.py::test_one"]


def test_a_repeated_failure_is_named_once():
    """A matrix reports the same node from three platforms. Three copies in one criterion
    is noise in the thing an agent has to read and act on."""
    with _log("FAILED tests/unit/test_a.py::test_one\n" * 3):
        assert failing_node_ids("1") == ["tests/unit/test_a.py::test_one"]


def test_an_unreadable_log_is_empty_not_an_exception():
    """A watcher that raised here would turn a red main into two problems. The failure is
    still recorded; only the node ids are missing."""
    with patch("subprocess.run", side_effect=OSError("gh missing")):
        assert failing_node_ids("1") == []


# ── the task a red main becomes ──────────────────────────────────────────────


def test_the_failing_tests_become_the_acceptance_criterion():
    """Nothing needs inventing: "is this fixed" already has an exact answer, and close
    executes the criterion anyway. A prose criterion would need a declared reason, and
    there is no reason here -- the check exists."""
    task = remediation_task(
        ["tests/unit/test_a.py::test_one", "tests/unit/test_b.py::test_two"],
        "https://github.com/o/r/actions/runs/9",
        "abc1234567",
    )
    assert task["acceptance_criteria"].startswith("TEST-CHECK: ")
    assert "tests/unit/test_a.py::test_one" in task["acceptance_criteria"]
    assert "tests/unit/test_b.py::test_two" in task["acceptance_criteria"]
    assert "abc1234" in task["title"]
    assert "https://github.com/o/r/actions/runs/9" in task["description"]


def test_a_long_failure_list_is_capped_and_says_so():
    """A criterion naming two hundred node ids is not something anybody picks up, and it
    stops being readable long before that. The count is still reported honestly."""
    nodes = [f"tests/unit/test_{i}.py::test_x" for i in range(40)]
    task = remediation_task(nodes, None, None)
    named = task["acceptance_criteria"].split()[1:]
    assert len(named) == MAX_NAMED_FAILURES
    assert "40 failing test(s)" in task["description"]
    assert "28 more" in task["description"]


def test_a_red_run_with_no_runnable_nodes_declares_instead_of_inventing():
    """The job may have failed in a gate step, or the failures may name files this merge
    deleted. A criterion written against a file that is not there can never fail for the
    right reason -- one in three TEST-CHECKs on the live authority named something
    unrunnable -- so the task carries a DECLARED REASON, the same escape any author gets.
    """
    task = remediation_task([], "https://github.com/o/r/actions/runs/9", "abc1234")
    assert "acceptance_criteria" not in task, "a criterion was invented for nothing to run"
    assert len(task["why"]) >= 20, "admission refuses a shrug, and rightly"
    assert "no runnable" in task["description"]


def test_unrunnable_node_ids_are_named_in_the_task():
    """An agent picking this up is owed what CI reported, even when none of it resolves
    here -- otherwise the task says a failure happened and nothing about which."""
    task = remediation_task(
        [],
        "https://github.com/o/r/actions/runs/9",
        "abc1234",
        unrunnable=["tests/unit/test_gone.py::test_x"],
    )
    assert "tests/unit/test_gone.py::test_x" in task["description"]


def test_a_node_whose_file_is_missing_is_filtered_out(tmp_path):
    """The filter is on the PATH, not the node: whether `::test_x` still exists inside a
    file is a question for the runner, and asking it here would mean importing the
    module."""
    from core.health.main_ci_watch import runnable_nodes

    (tmp_path / "tests" / "unit").mkdir(parents=True)
    (tmp_path / "tests" / "unit" / "test_here.py").write_text("\n", encoding="utf-8")
    nodes = ["tests/unit/test_here.py::test_a", "tests/unit/test_gone.py::test_b"]
    assert runnable_nodes(nodes, repo_root=tmp_path) == ["tests/unit/test_here.py::test_a"]


# ── which work orders this run decides ───────────────────────────────────────


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "studio.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE business_work_orders (
          work_order_id TEXT PRIMARY KEY, project_id TEXT, title TEXT, status TEXT,
          last_updated_at TEXT);
        """)
    rows = [
        ("wo-pushed-old", "p-1", "First out", "pushed", "2026-09-23T01:00:00"),
        ("wo-pushed-new", "p-1", "Second out", "pushed", "2026-09-23T02:00:00"),
        ("wo-working", "p-1", "Still being written", "in_progress", "2026-09-23T03:00:00"),
        ("wo-done", "p-1", "Already closed", "closed", "2026-09-23T00:00:00"),
    ]
    conn.executemany("INSERT INTO business_work_orders VALUES (?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    return path


def test_only_work_orders_at_pushed_are_awaiting_ci(db):
    """`pushed` is the link between a merge and the work that caused it. Work still being
    written is not waiting on this run, and work already closed has had its answer."""
    awaiting = work_orders_awaiting_ci(db)
    assert [w["work_order_id"] for w in awaiting] == ["wo-pushed-old", "wo-pushed-new"]


def test_they_come_oldest_first(db):
    """Two work orders waiting on one run are taken in the order they went out, so the
    one that has been unverified longest is dealt with first."""
    assert work_orders_awaiting_ci(db)[0]["work_order_id"] == "wo-pushed-old"


def test_an_unreadable_authority_is_empty_not_an_exception(tmp_path):
    """The watcher runs unattended. A missing database means it has nothing to act on,
    which is a quiet no-op rather than a crash nobody is there to read."""
    assert work_orders_awaiting_ci(tmp_path / "does-not-exist.db") == []


def test_the_project_id_comes_with_it(db):
    """create_task needs it, and reading it here avoids a second query per work order --
    and a second query is a second chance for the two to disagree about which project."""
    assert all(w["project_id"] == "p-1" for w in work_orders_awaiting_ci(db))


# ── a CI failure is a blocker, and both writers say so ───────────────────────


def test_the_projection_raises_priority_on_a_ci_failure():
    """Derived, not chosen. Main being red is a fact about the default branch, not a
    judgement about urgency -- and a level any writer may pick is `blocker` within a week,
    the same reason the rule registry makes its escape cost twenty characters."""
    import sqlite3 as _sq

    from core.projections.work_order_projection import WorkOrderProjection

    c = _sq.connect(":memory:")
    c.executescript("""
        CREATE TABLE business_work_orders (
          work_order_id TEXT PRIMARY KEY, project_id TEXT, milestone_id TEXT, title TEXT,
          status TEXT, created_at TEXT, started_at TEXT, closed_at TEXT, blocked_at TEXT,
          unblocked_at TEXT, block_reason TEXT, source_event_id TEXT, last_event_id TEXT,
          last_updated_at TEXT, description TEXT, work_order_type TEXT, updated_at TEXT,
          sequence_order INTEGER, originating_symptom TEXT, verify_status TEXT,
          verify_score REAL, verified_at TEXT,
          priority TEXT NOT NULL DEFAULT 'normal'
            CHECK (priority IN ('blocker','defect','normal','backlog')));
        """)
    proj = WorkOrderProjection()
    for event in ("work_order.created", "work_order.pushed", "work_order.ci_failed"):
        proj.handle(
            {
                "event_id": f"e-{event}",
                "event_type": event,
                "event_timestamp": "2026-09-23T00:00:00+00:00",
                "work_order_id": "wo-1",
                "project_id": "p-1",
                "payload": {"title": "t", "type": "infrastructure"},
            },
            c,
        )
    row = c.execute(
        "SELECT status, priority FROM business_work_orders WHERE work_order_id = 'wo-1'"
    ).fetchone()
    assert row == ("ci_issues", "blocker")


def test_the_direct_write_and_the_projection_agree():
    """Two writers, one fact. The row is written directly by advance_work_order and again
    by the projection on replay. If only the projection raised the priority, the queue
    would order correctly after a rebuild and wrongly until one happened -- which is the
    two-writers-disagreeing shape the status vocabulary exists to prevent, one column over.
    """
    import pathlib as _p

    source = _p.Path(__import__("core.work_orders.mutations", fromlist=["x"]).__file__).read_text(
        encoding="utf-8"
    )
    assert "priority = 'blocker'" in source, (
        "advance_work_order does not raise the priority, so a CI failure sorts as normal "
        "until something rebuilds the projection"
    )
