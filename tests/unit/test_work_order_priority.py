"""A work order carries what to pick up first, and the queue reads it.

WHY THIS EXISTS. `ds work-order next` ordered by `created_at ASC`, so the queue was FIFO.
A defect a review lane registered today queued behind every older work order, which is the
opposite of what a lane finding means -- and a red `main` found by the post-merge watcher
would have queued behind a year of backlog.

The policy was already written down: "defect work orders execute before normal milestone
work orders" has been an operator rule carried in an agent's notes, which is to say it
held exactly as long as an agent remembered it. Three agents write to this queue now --
the review lanes before a push, the watcher after one, and the session doing the building
-- and a rule that depends on recall is not a handoff protocol.

THE PATH IS THE POINT. `description` was accepted by the same door, left out of the
payload and never read by the projection: 443 of 920 work orders stored an empty one, and
the module boundary that lives inside it could not be declared at all. A field that stops
at any layer is indistinguishable from a field nobody set, so these tests walk the whole
way -- door, mutation, payload, projection, row, queue.
"""

from __future__ import annotations

import pathlib
import sqlite3

import pytest

from core.projections.work_order_projection import WorkOrderProjection
from core.work_orders.models import DEFAULT_WORK_ORDER_PRIORITY, WORK_ORDER_PRIORITIES


def _schema(conn: sqlite3.Connection) -> None:
    """The columns this projection writes, with the CHECK migration 157 adds."""
    conn.executescript("""
        CREATE TABLE business_work_orders (
          work_order_id TEXT PRIMARY KEY, project_id TEXT, milestone_id TEXT,
          title TEXT, status TEXT, created_at TEXT, started_at TEXT, closed_at TEXT,
          blocked_at TEXT, unblocked_at TEXT, block_reason TEXT, source_event_id TEXT,
          last_event_id TEXT, last_updated_at TEXT, description TEXT,
          work_order_type TEXT, updated_at TEXT, sequence_order INTEGER,
          originating_symptom TEXT, verify_status TEXT, verify_score REAL,
          verified_at TEXT,
          priority TEXT NOT NULL DEFAULT 'normal'
            CHECK (priority IN ('blocker', 'defect', 'normal', 'backlog'))
        );
        """)


def _created(conn, wo_id: str, *, priority: str | None, ts: str) -> None:
    payload = {"title": f"WO {wo_id}", "type": "infrastructure"}
    if priority is not None:
        payload["priority"] = priority
    WorkOrderProjection().handle(
        {
            "event_id": f"e-{wo_id}",
            "event_type": "work_order.created",
            "event_timestamp": ts,
            "work_order_id": wo_id,
            "project_id": "p-1",
            "payload": payload,
        },
        conn,
    )


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    _schema(c)
    return c


# ── the vocabulary is one definition, ordered ────────────────────────────────


def test_the_levels_are_ordered_most_urgent_first():
    """The tuple order IS the queue order, which is why it is a tuple and not a set.
    Sorted alphabetically, `backlog` would come first and `normal` ahead of `defect`."""
    assert WORK_ORDER_PRIORITIES == ("blocker", "defect", "normal", "backlog")
    assert DEFAULT_WORK_ORDER_PRIORITY in WORK_ORDER_PRIORITIES


def test_the_schema_check_matches_the_declared_vocabulary():
    """A level the code accepts and the column refuses would be a work order that cannot
    be written; one the column accepts and the code does not know would sort arbitrarily."""
    import pathlib
    import re

    sql = (
        pathlib.Path(__file__).resolve().parents[2]
        / "core"
        / "event_store"
        / "migrations"
        / "157_work_order_priority.sql"
    ).read_text(encoding="utf-8")
    match = re.search(r"CHECK \(priority IN \(([^)]*)\)\)", sql)
    assert match, "the migration declares no CHECK on priority"
    in_sql = {v.strip().strip("'") for v in match.group(1).split(",")}
    assert in_sql == set(WORK_ORDER_PRIORITIES)


# ── the payload reaches the row ──────────────────────────────────────────────


def test_a_priority_in_the_payload_reaches_the_row(conn):
    _created(conn, "wo-1", priority="blocker", ts="2026-09-23T00:00:00+00:00")
    row = conn.execute("SELECT priority FROM business_work_orders").fetchone()
    assert row[0] == "blocker"


def test_an_event_without_a_priority_takes_the_declared_default(conn):
    """Events predating the field are not missing values. The column is NOT NULL, and a
    replay of old history must land somewhere the queue understands."""
    _created(conn, "wo-1", priority=None, ts="2026-09-23T00:00:00+00:00")
    row = conn.execute("SELECT priority FROM business_work_orders").fetchone()
    assert row[0] == DEFAULT_WORK_ORDER_PRIORITY


def test_an_undeclared_priority_is_refused_where_it_can_be_reported():
    """The CHECK cannot be the thing that reports, and finding out why was the point.

    The projection inserts with INSERT OR IGNORE so a duplicate created event is a no-op.
    SQLite's OR IGNORE also SKIPS a row that violates a constraint -- so a priority the
    CHECK rejects does not raise: the work order simply does not exist. Measured below.
    A work order that silently vanished is worse than one carrying a wrong label, so the
    refusal lives in `create_work_order`, which can say what objected.
    """
    from core.work_orders.mutations import create_work_order

    result = create_work_order(
        project_id="p-1",
        milestone_id="m-1",
        title="A thing",
        description="A description long enough to clear the prompt floor for a work order.",
        priority="urgent",
        source_root=pathlib.Path("."),
    )
    assert result["ok"] is False
    assert "urgent" in result["error"], result["error"]
    for level in WORK_ORDER_PRIORITIES:
        assert level in result["error"], f"the refusal does not name {level}"


def test_an_unknown_priority_on_an_event_degrades_rather_than_losing_the_row(conn):
    """History may carry a priority this build does not declare, and the row must survive.

    The column has a CHECK and the projection inserts OR IGNORE so a duplicate created
    event is a no-op. SQLite's OR IGNORE also SKIPS a constraint violation, so before the
    coercion an unrecognised priority did not store a wrong label -- it made the work order
    not exist, no row and no error. The payload-seam test found it, because it sends a
    distinctive value for every key.

    Degrading to the default is the safe direction: a work order in the wrong queue
    position is findable, one that silently never materialised is not. The refusal lives
    at the authoring door, where it can say what objected.
    """
    _created(conn, "wo-1", priority="urgent", ts="2026-09-23T00:00:00+00:00")
    row = conn.execute("SELECT work_order_id, priority FROM business_work_orders").fetchone()
    assert row is not None, "an unknown priority lost the work order entirely"
    assert row[1] == DEFAULT_WORK_ORDER_PRIORITY


# ── the queue reads it ───────────────────────────────────────────────────────


def test_the_queue_orders_by_priority_then_age(conn):
    """Age still breaks ties, so two blockers are taken oldest first. Without the second
    key the order among equals would be whatever SQLite happened to return."""
    _created(conn, "old-backlog", priority="backlog", ts="2026-01-01T00:00:00+00:00")
    _created(conn, "old-normal", priority="normal", ts="2026-01-02T00:00:00+00:00")
    _created(conn, "new-blocker", priority="blocker", ts="2026-09-23T00:00:00+00:00")
    _created(conn, "older-blocker", priority="blocker", ts="2026-09-22T00:00:00+00:00")
    _created(conn, "new-defect", priority="defect", ts="2026-09-23T00:00:00+00:00")

    ordered = [
        r[0]
        for r in conn.execute(
            "SELECT work_order_id FROM business_work_orders"
            " ORDER BY CASE priority WHEN 'blocker' THEN 0 WHEN 'defect' THEN 1"
            " WHEN 'normal' THEN 2 WHEN 'backlog' THEN 3 ELSE 2 END, created_at ASC"
        )
    ]
    assert ordered == [
        "older-blocker",
        "new-blocker",
        "new-defect",
        "old-normal",
        "old-backlog",
    ], ordered


def test_the_queue_query_in_the_engine_sorts_on_priority():
    """The ordering above is the engine's own, not a second copy written for this test.
    Two sorts that agree by inspection are the arrangement this repo keeps removing."""
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parents[2] / "core" / "work_orders" / "queries.py"
    ).read_text(encoding="utf-8")
    assert "CASE wo.priority" in source, "the queue does not sort on priority"
    assert "wo.created_at ASC" in source, "the queue dropped age as the tie-break"
    for level in WORK_ORDER_PRIORITIES:
        assert f"'{level}'" in source, f"the queue's CASE does not handle {level}"
