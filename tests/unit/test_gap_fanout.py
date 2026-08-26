"""WO-GAP-FANOUT: the verify plane must not create work faster than it can be closed.

MEASURED 2026-08-21 on the live authority, which is why this work order exists:

    work orders created 08-19..08-21 : 118
    closed in the same window        :  43      net +75, 140 open

    duplicate auto-spawned titles:
      x11  "Add missing adversarial tests for durable/reachable failure modes"
      x8   "Add missing test coverage"
    -> 19 of the 25 auto-spawned work orders were the SAME TWO findings.

ROOT CAUSE, proven rather than guessed: ``_gap_key`` returns
``{reviewed_work_order_id}::{category}``, so a generic finding gets a different key on
every reviewed work order. The eleven duplicates carried eleven distinct gap-key
markers, identical after the ``::``. Dedup worked exactly as written; the key was one
field too specific.

A PRIOR WORK ORDER FOUND THIS AND FIXED IT TOO NARROWLY. WO-GAP-DEDUPE-CLASS added
``_ADVISORY_PROJECT_WIDE_CATEGORIES`` — an allowlist that held exactly one entry while
two unlisted phrasings produced the fan-out above. So the allowlist is extended AND
backed by a rule that needs no prediction.

The operator's report was that something else always gets surfaced by the review agent,
and that this is why scheduled work does not get finished. That is not a reviewer being
unreasonable. It is 2.7 work orders created per one closed.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders.verify_gaps import (
    _ADVISORY_PROJECT_WIDE_CATEGORIES,
    _PROJECT_WIDE_AFTER_N_OPEN_SPAWNS,
    _falsification_to_gaps,
    _gap_key,
    _insert_gap_work_orders,
)

_NOW = "2026-08-21T00:00:00+00:00"

# The exact titles measured in the live authority, so this suite tracks the real classes
# rather than invented ones.
_ADVERSARIAL = "Add missing adversarial tests for durable/reachable failure modes"
_COVERAGE = "Add missing test coverage"


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "state" / "studio.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(path)
    return path


def _project(conn: sqlite3.Connection) -> str:
    project_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (project_id, "P", "", "active", _NOW, _NOW),
    )
    return project_id


def _reviewed_wo(conn: sqlite3.Connection, project_id: str) -> str:
    wo_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, work_order_type,"
        "  status, created_at, updated_at)"
        " VALUES (?,?,NULL,'reviewed','d','infrastructure','in_progress',?,?)",
        (wo_id, project_id, _NOW, _NOW),
    )
    return wo_id


def _spawn(conn: sqlite3.Connection, project_id: str, reviewed: str, title: str) -> list[dict]:
    return _insert_gap_work_orders(
        conn,
        gaps=[{"title": title, "description": "d", "work_order_type": "cleanup", "tasks": []}],
        project_id=project_id,
        milestone_id=None,
        reviewed_work_order_id=reviewed,
        reviewed_wo_title="reviewed",
        reviewed_wo_sequence=1,
    )


def _open_count(conn: sqlite3.Connection, title: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM business_work_orders"
        " WHERE title = ? AND status IN ('created','in_progress')",
        (title,),
    ).fetchone()[0]


# ── Task 1: the generic class dedups project-wide ─────────────────────────────


def test_a_generic_class_spawns_once_project_wide(db):
    """The x11 case. Eleven different reviewed work orders, one tracking work order.

    Drives the real ``_insert_gap_work_orders`` against a real bootstrapped authority,
    because the defect lived in the interaction between the key and the lookup query — a
    stubbed spawner would have reproduced neither.
    """
    conn = sqlite3.connect(str(db))
    project_id = _project(conn)

    for _ in range(11):
        _spawn(conn, project_id, _reviewed_wo(conn, project_id), _ADVERSARIAL)
    conn.commit()

    assert (
        _open_count(conn, _ADVERSARIAL) == 1
    ), "eleven reviewed work orders produced eleven duplicates before this fix"
    conn.close()


def test_the_second_measured_class_also_dedups(db):
    """The x8 case. Its producer (``coverage_gaps`` from the correctness grader) emits no
    severity field at all, so there is nothing to filter on — project-wide dedup is the
    correct control there rather than an invented severity filter."""
    conn = sqlite3.connect(str(db))
    project_id = _project(conn)
    for _ in range(8):
        _spawn(conn, project_id, _reviewed_wo(conn, project_id), _COVERAGE)
    conn.commit()
    assert _open_count(conn, _COVERAGE) == 1
    conn.close()


def test_a_third_occurrence_self_corrects_without_an_allowlist_entry(db):
    """THE BACKSTOP, and the reason the allowlist alone cannot hold.

    WO-GAP-DEDUPE-CLASS added the allowlist with one entry; two later phrasings sailed
    past it and fanned out nineteen times. A class the grader has not phrased yet will do
    the same. So a category with N open spawns across different reviewed work orders
    becomes project-wide whatever it is called — bounding an unknown future class at N
    instead of leaving it unbounded.
    """
    unlisted = "Some phrasing nobody has predicted yet"
    assert "some-phrasing-nobody-has-predicted-yet" not in _ADVISORY_PROJECT_WIDE_CATEGORIES

    conn = sqlite3.connect(str(db))
    project_id = _project(conn)
    for _ in range(6):
        _spawn(conn, project_id, _reviewed_wo(conn, project_id), unlisted)
    conn.commit()

    open_now = _open_count(conn, unlisted)
    assert open_now == _PROJECT_WIDE_AFTER_N_OPEN_SPAWNS, (
        f"an unlisted class must self-correct at {_PROJECT_WIDE_AFTER_N_OPEN_SPAWNS},"
        f" got {open_now} open after six reviews"
    )
    conn.close()


# ── Task 2: a content-specific gap must STILL scope to its work order ─────────


def test_a_content_specific_gap_stays_scoped_to_its_work_order(db):
    """The converse, and the reason the key was written this way in the first place.

    A finding like "task 3 was never implemented" is about ONE work order. Widening
    everything to dedup project-wide would merge distinct per-WO findings and hide real
    work — strictly worse than the fan-out. The backstop only fires on a class that has
    demonstrably repeated, so a genuine per-WO gap is never merged on first appearance.
    """
    conn = sqlite3.connect(str(db))
    project_id = _project(conn)
    wo_a, wo_b = _reviewed_wo(conn, project_id), _reviewed_wo(conn, project_id)

    gap_a = {"title": "Implement task 3 of the delivery boundary", "category": "task-3-boundary"}
    gap_b = {"title": "Implement task 3 of the hook accounting", "category": "task-3-hooks"}
    key_a = _gap_key(wo_a, gap_a, conn=conn, project_id=project_id)
    key_b = _gap_key(wo_b, gap_b, conn=conn, project_id=project_id)

    assert key_a.startswith(wo_a), "a content-specific gap keeps its reviewed-WO scope"
    assert key_b.startswith(wo_b)
    assert key_a != key_b, "two different per-WO findings must not collapse into one"
    conn.close()


def test_the_same_specific_gap_on_the_same_work_order_still_dedups(db):
    """Re-reviewing one work order must not duplicate its own findings — the original
    guarantee, unchanged by this fix."""
    conn = sqlite3.connect(str(db))
    project_id = _project(conn)
    reviewed = _reviewed_wo(conn, project_id)
    title = "Wire the specific thing this one work order missed"
    _spawn(conn, project_id, reviewed, title)
    _spawn(conn, project_id, reviewed, title)
    conn.commit()
    assert _open_count(conn, title) == 1
    conn.close()


def test_the_backstop_cannot_break_a_verify(db):
    """A dedup backstop that raises would take verify down with it, which is a worse
    outcome than the fan-out it prevents. An unusable connection degrades to the
    original per-WO key rather than erroring."""

    class Hostile:
        def execute(self, *_a, **_k):
            raise sqlite3.OperationalError("no such table")

    reviewed = str(uuid.uuid4())
    key = _gap_key(
        reviewed,
        {"title": "anything", "category": "anything"},
        conn=Hostile(),
        project_id="p",
    )
    assert key.startswith(reviewed), "it falls back to the scoped key instead of raising"


# ── Task 4: severity floor ────────────────────────────────────────────────────


def test_a_warning_severity_finding_does_not_spawn_a_work_order():
    """Already true for every producer that HAS a severity field, and pinned here because
    nothing asserted it.

    A warning that becomes a work order is how a reviewer's observation turns into
    scheduling debt. Warning-severity falsification scenarios stay in the
    unverified-risk ledger, which already exists and already surfaces at close.
    """
    warning_only = [
        {"status": "PROPOSED", "severity": "warning", "scenario": "a milder worst case"},
        {"status": "UNVERIFIED", "severity": "error", "scenario": "cannot be tested yet"},
    ]
    assert (
        _falsification_to_gaps(warning_only) == []
    ), "only error-severity PROPOSED scenarios may spawn work"

    with_error = [
        {"status": "PROPOSED", "severity": "error", "scenario": "crash mid-write is untested"},
    ]
    assert _falsification_to_gaps(with_error), "an error-severity testable gap still spawns"
