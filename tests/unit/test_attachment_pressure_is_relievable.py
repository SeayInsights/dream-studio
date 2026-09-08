"""Attachment pressure must be relievable, not only warned about.

WO 376ec1dd. WO-GAP-FANOUT stopped gaps SPAWNING sibling work orders by ATTACHING them as
tasks to the work order that owns them. That is the right shape -- a gap on an open work
order is that work order's remaining scope -- but it moved the pressure rather than
bounding it, and the tooling did not follow.

Measured 2026-09-08: ``ds work-order drain-gaps`` reported "No gap category has more than
one open spawn. Nothing to drain." while 317 pending tasks sat on in-progress work orders.
With the attached form visible, the same command found 32 duplicated categories and 340
duplicate tasks -- "add-missing-adversarial-tests" attached 82 times across 15 work orders,
"add-missing-test-coverage" 74 times across 14. The verdict printed an ATTACHMENT PRESSURE
warning naming carry-over as the remedy, and nothing could act on it.

Grouping is by the CATEGORY half of the key, ACROSS work orders. That is the whole point of
a category: a generic finding is one piece of work however many reviews surfaced it, and
keying on the reviewed work order is what made eleven duplicates carry eleven distinct keys
in the original fan-out.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.work_orders.verify_gaps import drain_fanned_out_categories

PROJECT = "proj-drain"


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    """A real authority built by the real migration chain."""
    from core.config.sqlite_bootstrap import bootstrap_database

    db_path = tmp_path / "studio.db"
    bootstrap_database(db_path)
    connection = sqlite3.connect(str(db_path))
    connection.execute(
        "INSERT INTO business_projects (project_id, name, status, created_at, updated_at)"
        " VALUES (?, 'Drain', 'active', '2026-09-01T00:00:00Z', '2026-09-01T00:00:00Z')",
        (PROJECT,),
    )
    yield connection
    connection.close()


def _work_order(conn: sqlite3.Connection, wo_id: str, *, status: str = "in_progress") -> None:
    conn.execute(
        "INSERT INTO business_work_orders (work_order_id, project_id, title, description,"
        " status, work_order_type, sequence_order, created_at, updated_at)"
        " VALUES (?, ?, ?, '', ?, 'infrastructure', 1, '2026-09-01T00:00:00Z',"
        " '2026-09-01T00:00:00Z')",
        (wo_id, PROJECT, f"WO {wo_id}", status),
    )


def _attached_task(
    conn: sqlite3.Connection,
    task_id: str,
    wo_id: str,
    category: str,
    *,
    reviewed: str = "rev-1",
    status: str = "pending",
    created_at: str = "2026-09-02T00:00:00Z",
) -> None:
    conn.execute(
        "INSERT INTO business_tasks (task_id, work_order_id, project_id, title, description,"
        " status, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            task_id,
            wo_id,
            PROJECT,
            f"Fix {category}",
            f"A finding. [gap-attached: {reviewed}::{category}]",
            status,
            created_at,
            created_at,
        ),
    )


def test_drain_gaps_sees_attached_tasks(conn):
    """The symptom check for WO 376ec1dd.

    The same category attached to two DIFFERENT work orders, which is the measured shape --
    twelve titles appeared on two work orders each. Before the fix this reported nothing to
    drain.
    """
    _work_order(conn, "wo-a")
    _work_order(conn, "wo-b")
    _attached_task(conn, "t-1", "wo-a", "add-missing-test-coverage", reviewed="rev-1")
    _attached_task(
        conn,
        "t-2",
        "wo-b",
        "add-missing-test-coverage",
        reviewed="rev-2",
        created_at="2026-09-03T00:00:00Z",
    )

    result = drain_fanned_out_categories(conn, PROJECT, apply=False)

    assert result["attached_categories_fanned_out"] == 1, (
        "the attached form is invisible again -- drain-gaps sees only spawned siblings, so"
        " the pressure it warns about cannot be relieved"
    )
    assert result["attached_would_cancel"] == 1
    item = result["attached_plan"][0]
    assert item["category"] == "add-missing-test-coverage"
    assert item["keep"] == "t-1", "the earliest-created duplicate must survive"
    assert item["cancel"] == ["t-2"]
    assert item["work_orders"] == ["wo-a", "wo-b"], "the report must name both work orders"


def test_a_single_attachment_is_not_drained(conn):
    """The control. One attachment of a category is scope, not duplication -- and a drain
    that cancelled it would delete real remaining work."""
    _work_order(conn, "wo-a")
    _attached_task(conn, "t-1", "wo-a", "add-missing-test-coverage")

    result = drain_fanned_out_categories(conn, PROJECT, apply=False)
    assert result["attached_categories_fanned_out"] == 0
    assert result["attached_would_cancel"] == 0


def test_preview_changes_nothing(conn):
    """A destructive maintenance action must be readable before it runs."""
    _work_order(conn, "wo-a")
    _work_order(conn, "wo-b")
    _attached_task(conn, "t-1", "wo-a", "cat")
    _attached_task(conn, "t-2", "wo-b", "cat", created_at="2026-09-03T00:00:00Z")

    drain_fanned_out_categories(conn, PROJECT, apply=False)

    statuses = dict(conn.execute("SELECT task_id, status FROM business_tasks").fetchall())
    assert statuses == {"t-1": "pending", "t-2": "pending"}


def test_apply_cancels_the_duplicate_and_records_why(conn):
    _work_order(conn, "wo-a")
    _work_order(conn, "wo-b")
    _attached_task(conn, "t-1", "wo-a", "cat")
    _attached_task(conn, "t-2", "wo-b", "cat", created_at="2026-09-03T00:00:00Z")

    result = drain_fanned_out_categories(conn, PROJECT, apply=True)
    assert result["applied"] is True
    assert result["attached_cancelled"] == 1

    row = conn.execute(
        "SELECT status, description FROM business_tasks WHERE task_id = 't-2'"
    ).fetchone()
    assert row[0] == "cancelled"
    assert "t-1" in row[1], "the cancelled duplicate must name what absorbed it"

    survivor = conn.execute("SELECT status FROM business_tasks WHERE task_id = 't-1'").fetchone()
    assert survivor[0] == "pending", "the survivor must be left alone"


def test_apply_is_idempotent(conn):
    """Running it twice must not cancel the survivor: a drained duplicate is no longer open,
    so the second run has nothing to group."""
    _work_order(conn, "wo-a")
    _work_order(conn, "wo-b")
    _attached_task(conn, "t-1", "wo-a", "cat")
    _attached_task(conn, "t-2", "wo-b", "cat", created_at="2026-09-03T00:00:00Z")

    drain_fanned_out_categories(conn, PROJECT, apply=True)
    second = drain_fanned_out_categories(conn, PROJECT, apply=True)

    assert second["attached_cancelled"] == 0
    assert (
        conn.execute("SELECT status FROM business_tasks WHERE task_id = 't-1'").fetchone()[0]
        == "pending"
    )


def test_a_completed_duplicate_is_not_counted(conn):
    """Already-satisfied work is already drained. Counting it would inflate the report with
    work nobody has to do -- and one such duplicate had been satisfied on one work order
    while the other still carried it."""
    _work_order(conn, "wo-a")
    _work_order(conn, "wo-b")
    _attached_task(conn, "t-1", "wo-a", "cat", status="complete")
    _attached_task(conn, "t-2", "wo-b", "cat", created_at="2026-09-03T00:00:00Z")

    result = drain_fanned_out_categories(conn, PROJECT, apply=False)
    assert result["attached_categories_fanned_out"] == 0


def test_tasks_on_a_closed_work_order_are_not_drained(conn):
    """A closed work order's tasks are history, not queue."""
    _work_order(conn, "wo-a", status="closed")
    _work_order(conn, "wo-b", status="closed")
    _attached_task(conn, "t-1", "wo-a", "cat")
    _attached_task(conn, "t-2", "wo-b", "cat", created_at="2026-09-03T00:00:00Z")

    result = drain_fanned_out_categories(conn, PROJECT, apply=False)
    assert result["attached_categories_fanned_out"] == 0


def test_an_unattached_task_is_never_touched(conn):
    """Only tasks carrying the gap marker are gap tasks. An ordinary task duplicated by
    coincidence of title is real work."""
    _work_order(conn, "wo-a")
    _work_order(conn, "wo-b")
    for task_id, wo in (("t-1", "wo-a"), ("t-2", "wo-b")):
        conn.execute(
            "INSERT INTO business_tasks (task_id, work_order_id, project_id, title,"
            " description, status, created_at, updated_at)"
            " VALUES (?, ?, ?, 'Write the thing', 'no marker here', 'pending',"
            " '2026-09-02T00:00:00Z', '2026-09-02T00:00:00Z')",
            (task_id, wo, PROJECT),
        )

    result = drain_fanned_out_categories(conn, PROJECT, apply=False)
    assert result["attached_categories_fanned_out"] == 0


def test_the_two_forms_are_reported_separately(conn):
    """They cancel different things -- a work order versus a task on one -- and merging the
    counts is how a reader thinks a work order was cancelled when a task was."""
    _work_order(conn, "wo-a")
    _work_order(conn, "wo-b")
    _attached_task(conn, "t-1", "wo-a", "cat")
    _attached_task(conn, "t-2", "wo-b", "cat", created_at="2026-09-03T00:00:00Z")

    result = drain_fanned_out_categories(conn, PROJECT, apply=False)
    assert result["categories_fanned_out"] == 0, "no sibling work orders were spawned here"
    assert result["attached_categories_fanned_out"] == 1
    assert "plan" in result and "attached_plan" in result
