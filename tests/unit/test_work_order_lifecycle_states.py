"""A work order is not done until `main` is green.

WHAT THIS CHANGES. A work order went `created -> in_progress -> closed`, so "I think this
is finished" and "this actually worked" were the same event, and closure landed at the
moment of least evidence: before the review lanes had looked and before CI had run. Three
times in one day a work order's own merge put main red and the work was declared done
anyway, because the only thing between the two was an operator noticing a line of output.

Three statuses now sit between working and done -- `in_review`, `pushed`, `ci_issues` --
and close refuses while main is known red.
"""

from __future__ import annotations

import pathlib
import sqlite3
from unittest.mock import patch

import pytest

from core.projections.work_order_projection import WorkOrderProjection
from core.work_orders.task_status import (
    CANONICAL_WORK_ORDER_STATUSES,
    TERMINAL_WORK_ORDER_STATUSES,
    WORK_ORDER_EVENT_STATUS,
    WORK_ORDER_STATUS_EVENT,
)

_NEW = ("in_review", "pushed", "ci_issues")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript("""
        CREATE TABLE business_work_orders (
          work_order_id TEXT PRIMARY KEY, project_id TEXT, milestone_id TEXT, title TEXT,
          status TEXT, created_at TEXT, started_at TEXT, closed_at TEXT, blocked_at TEXT,
          unblocked_at TEXT, block_reason TEXT, source_event_id TEXT, last_event_id TEXT,
          last_updated_at TEXT, description TEXT, work_order_type TEXT, updated_at TEXT,
          sequence_order INTEGER, originating_symptom TEXT, verify_status TEXT,
          verify_score REAL, verified_at TEXT,
          -- Migration 157. The projection writes it, and this fixture met the hazard that
          -- migration documents: the INSERT is OR IGNORE, so a column the fixture lacks
          -- does not raise -- the row silently is not written at all.
          priority TEXT NOT NULL DEFAULT 'normal'
            CHECK (priority IN ('blocker', 'defect', 'normal', 'backlog')));
        """)
    return c


def _apply(conn, event_type: str, *, wo="wo-1", ts="2026-09-23T00:00:00+00:00") -> None:
    WorkOrderProjection().handle(
        {
            "event_id": f"e-{event_type}-{ts}",
            "event_type": event_type,
            "event_timestamp": ts,
            "work_order_id": wo,
            "project_id": "p-1",
            "payload": {"title": "A work order", "type": "infrastructure"},
        },
        conn,
    )


def _status(conn, wo="wo-1") -> str | None:
    row = conn.execute(
        "SELECT status FROM business_work_orders WHERE work_order_id = ?", (wo,)
    ).fetchone()
    return row[0] if row else None


# ── the vocabulary moved together ────────────────────────────────────────────


@pytest.mark.parametrize("status", _NEW)
def test_each_new_status_is_declared_in_all_three_places(status):
    """The three declarations answer different questions and are checked against each
    other: what a replay can produce, which event a backfill emits for a row sitting at
    this status, and which status an event lands on. A status in one and not the others
    is the shape `a-vocabulary-has-one-definition-per-domain` exists to catch."""
    assert status in CANONICAL_WORK_ORDER_STATUSES
    event = WORK_ORDER_STATUS_EVENT[status]
    assert event, f"{status} has no event a backfill could emit"
    assert WORK_ORDER_EVENT_STATUS[event] == status


@pytest.mark.parametrize("status", _NEW)
def test_none_of_the_new_statuses_is_terminal(status):
    """`pushed` is the one worth stating: the work is on GitHub and feels finished, and it
    is exactly the point at which it is not. A terminal `pushed` would let a milestone
    close over work whose CI had not run."""
    assert status not in TERMINAL_WORK_ORDER_STATUSES


# ── a replay reaches them ────────────────────────────────────────────────────


@pytest.mark.parametrize("status", _NEW)
def test_a_replay_lands_on_each_new_status(conn, status):
    _apply(conn, "work_order.created")
    _apply(conn, WORK_ORDER_STATUS_EVENT[status])
    assert _status(conn) == status


def test_the_round_trip_through_review_returns_to_in_progress(conn):
    """The loop the review lanes drive: findings come back as tasks on this same work
    order, so the work order returns to in_progress rather than being closed and a new one
    opened. `work_order.started` carries it, because a fourth spelling of "work is
    happening" is what the event map exists to prevent."""
    _apply(conn, "work_order.created")
    _apply(conn, "work_order.started")
    _apply(conn, "work_order.review_requested")
    assert _status(conn) == "in_review"
    _apply(conn, "work_order.started", ts="2026-09-23T01:00:00+00:00")
    assert _status(conn) == "in_progress"


def test_started_at_survives_a_round_trip(conn):
    """A work order is started once. Resetting the clock on every return from review would
    lose how long the work actually took, and the round trips are the thing worth
    measuring."""
    _apply(conn, "work_order.created")
    _apply(conn, "work_order.started", ts="2026-09-23T00:00:00+00:00")
    first = conn.execute("SELECT started_at FROM business_work_orders").fetchone()[0]
    _apply(conn, "work_order.review_requested", ts="2026-09-23T02:00:00+00:00")
    _apply(conn, "work_order.pushed", ts="2026-09-23T03:00:00+00:00")
    assert conn.execute("SELECT started_at FROM business_work_orders").fetchone()[0] == first


# ── close waits for CI ───────────────────────────────────────────────────────


def _ci(status: str | None):
    """Patch the live CI read with one answer."""
    state = {"status": status, "sha": "abc1234"} if status else {}
    return patch("core.health.main_ci.main_ci_status", return_value=state)


def test_a_known_red_main_blocks_the_close():
    """The whole point. The read was already here and already live; it was attached to the
    result after the row had been written, as an advisory an operator might notice."""
    from core.work_orders.close_main import main_ci_blocks_close

    with _ci("failure"):
        blocked = main_ci_blocks_close(pathlib.Path("."))
    assert blocked is not None
    assert blocked["status"] == "failure"


@pytest.mark.parametrize("status", ["success", "running", "unknown", None])
def test_anything_that_is_not_a_known_failure_does_not_block(status):
    """An absent `gh`, a rate limit, or a run nobody has started yet all read unknown.
    Blocking there would make closing depend on network weather, and a check nobody can
    satisfy is bypassed by habit until it means nothing."""
    from core.work_orders.close_main import main_ci_blocks_close

    with _ci(status):
        assert main_ci_blocks_close(pathlib.Path(".")) is None


def test_an_unreadable_answer_is_unknown_not_a_block():
    """The same reasoning one layer down: a raising `gh` is no more a red main than a
    silent one, and failing closed here would make a network blip a work stoppage."""
    from core.work_orders.close_main import main_ci_blocks_close

    with patch("core.health.main_ci.main_ci_status", side_effect=RuntimeError("gh exploded")):
        assert main_ci_blocks_close(pathlib.Path(".")) is None


def test_force_is_the_declared_escape():
    """Closing over a red main someone else caused is legitimate and must not require
    editing code. The bypass is recorded as gate.bypassed, which is why it may exist."""
    from core.work_orders.close_main import main_ci_blocks_close

    with _ci("failure"):
        assert main_ci_blocks_close(pathlib.Path("."), force=True) is None


def test_the_close_path_consults_the_predicate():
    """A predicate nothing calls is the disconnected-verification shape this repo keeps
    finding. Asserted on the call site, since driving a full close needs a database, a
    project, a milestone, tasks and passing gates."""
    source = pathlib.Path(
        __import__("core.work_orders.close_main", fromlist=["x"]).__file__
    ).read_text(encoding="utf-8")
    assert "main_ci_blocks_close(source_root, force=force)" in source
    assert "main_ci_green" in source, "the refusal does not name itself as a failure"
