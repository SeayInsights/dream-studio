"""Regression test: create_milestone order_index must be persisted.

Bug: MilestoneProjection._handle_created reads `payload.get("order_index") or 0`,
so a missing order_index in the payload always materialized as 0.
Fix: mutations.create_milestone now includes order_index in the emitted payload.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.projections.milestone_projection import MilestoneProjection

PROJECT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
MILESTONE_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
NOW = "2026-06-09T00:00:00.000000Z"
EVENT_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"


@pytest.fixture()
def db_conn(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "state" / "studio.db"
    db_path.parent.mkdir(parents=True)
    bootstrap_database(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?, 'Test', 'desc', 'active', ?, ?)",
        (PROJECT_ID, NOW, NOW),
    )
    conn.commit()
    yield conn
    conn.close()


def test_order_index_persisted(db_conn: sqlite3.Connection) -> None:
    """order_index from payload is written to the business_milestones row."""
    projection = MilestoneProjection()
    projection._handle_created(
        conn=db_conn,
        milestone_id=MILESTONE_ID,
        project_id=PROJECT_ID,
        payload={
            "title": "Alpha",
            "description": "First cut",
            "order_index": 5,
            "status": "pending",
        },
        event_id=EVENT_ID,
        ts=NOW,
        now=NOW,
    )
    db_conn.commit()

    row = db_conn.execute(
        "SELECT order_index FROM business_milestones WHERE milestone_id = ?",
        (MILESTONE_ID,),
    ).fetchone()
    assert row is not None, "milestone row was not created"
    assert row["order_index"] == 5, f"expected order_index=5, got {row['order_index']}"


def test_order_index_zero_when_payload_zero(db_conn: sqlite3.Connection) -> None:
    """order_index=0 is explicitly persisted (not treated as falsy)."""
    projection = MilestoneProjection()
    projection._handle_created(
        conn=db_conn,
        milestone_id=MILESTONE_ID,
        project_id=PROJECT_ID,
        payload={"title": "Alpha", "order_index": 0, "status": "pending"},
        event_id=EVENT_ID,
        ts=NOW,
        now=NOW,
    )
    db_conn.commit()

    row = db_conn.execute(
        "SELECT order_index FROM business_milestones WHERE milestone_id = ?",
        (MILESTONE_ID,),
    ).fetchone()
    assert row is not None
    assert row["order_index"] == 0


def test_existing_milestones_unaffected(db_conn: sqlite3.Connection) -> None:
    """Milestones created before this fix (order_index=0) are not changed by new inserts."""
    projection = MilestoneProjection()

    existing_milestone_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
    db_conn.execute(
        "INSERT INTO business_milestones"
        " (milestone_id, project_id, title, status, order_index, created_at, updated_at)"
        " VALUES (?, ?, 'Old', 'pending', 0, ?, ?)",
        (existing_milestone_id, PROJECT_ID, NOW, NOW),
    )
    db_conn.commit()

    # Create a new milestone with a different order_index
    projection._handle_created(
        conn=db_conn,
        milestone_id=MILESTONE_ID,
        project_id=PROJECT_ID,
        payload={"title": "New", "order_index": 3, "status": "pending"},
        event_id=EVENT_ID,
        ts=NOW,
        now=NOW,
    )
    db_conn.commit()

    old_row = db_conn.execute(
        "SELECT order_index FROM business_milestones WHERE milestone_id = ?",
        (existing_milestone_id,),
    ).fetchone()
    new_row = db_conn.execute(
        "SELECT order_index FROM business_milestones WHERE milestone_id = ?",
        (MILESTONE_ID,),
    ).fetchone()

    assert old_row["order_index"] == 0, "existing milestone order_index was mutated"
    assert (
        new_row["order_index"] == 3
    ), f"new milestone has wrong order_index: {new_row['order_index']}"
