"""WO-DELETED-TERMINAL-PRECONDITIONS: a deleted work order is TERMINAL and must
not block starting a later work order.

Sibling of ac6d3a53 (which fixed only milestone close). The WO start/sequence
checks still read ``NOT IN ('closed', 'cancelled')`` — omitting ``'deleted'`` —
so a WO retired via a ``work_order.deleted`` event (status='deleted') was counted
as outstanding and blocked the entire next milestone (surfaced: the deleted WO
48411bae blocked every "Dream Studio Rigor" work order). All four lifecycle checks
now read the single shared ``TERMINAL_WO_STATUSES`` (closed / cancelled / deleted).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders.models import TERMINAL_WO_STATUSES
from core.work_orders.start_brief import read_work_order_brief
from core.work_orders.start_shared import _check_sequence_order

REPO = Path(__file__).resolve().parents[2]
NOW = "2026-07-24T00:00:00Z"
PROJECT_ID = "p-wodel"
MS_EARLY = "m-wodel-early"  # order_index 10
MS_LATE = "m-wodel-late"  # order_index 20
TARGET_WO = "wo-wodel-target"  # lives in the later milestone


def _insert_wo(conn, wo_id, milestone_id, status, *, seq=None):
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id,project_id,milestone_id,title,description,status,"
        " work_order_type,sequence_order,created_at,updated_at)"
        " VALUES (?,?,?,?,NULL,?,'infrastructure',?,?,?)",
        (wo_id, PROJECT_ID, milestone_id, wo_id, status, seq, NOW, NOW),
    )


@pytest.fixture
def home(tmp_path: Path) -> Path:
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO business_projects (project_id,name,description,status,created_at,updated_at)"
            " VALUES (?,'P','','active',?,?)",
            (PROJECT_ID, NOW, NOW),
        )
        for ms_id, order_index in ((MS_EARLY, 10), (MS_LATE, 20)):
            conn.execute(
                "INSERT INTO business_milestones"
                " (milestone_id,project_id,title,order_index,status,created_at,updated_at)"
                " VALUES (?,?,?,?,'active',?,?)",
                (ms_id, PROJECT_ID, ms_id, order_index, NOW, NOW),
            )
        # Earlier milestone: two TERMINAL WOs (one deleted, one closed) — neither
        # must count as blocking the later milestone's work order.
        _insert_wo(conn, "wo-early-deleted", MS_EARLY, "deleted")
        _insert_wo(conn, "wo-early-closed", MS_EARLY, "closed")
        # Later milestone: the WO we want to start.
        _insert_wo(conn, TARGET_WO, MS_LATE, "created")
        conn.commit()
    finally:
        conn.close()
    return tmp_path


def test_deleted_earlier_milestone_wo_does_not_block_start(home: Path):
    """The earlier milestone holds only terminal WOs (deleted + closed), so the
    later WO's blocking-milestone count is 0 and it is startable."""
    brief = read_work_order_brief(work_order_id=TARGET_WO, source_root=REPO, dream_studio_home=home)
    assert brief.get("ok") is True, brief
    assert brief["blocking_milestone_count"] == 0, brief


def test_genuine_open_earlier_wo_still_blocks(home: Path):
    """Guard against over-correction: a non-terminal (created) WO in an earlier
    milestone must still be counted as blocking."""
    db = home / "state" / "studio.db"
    conn = sqlite3.connect(str(db))
    try:
        _insert_wo(conn, "wo-early-open", MS_EARLY, "created")
        conn.commit()
    finally:
        conn.close()

    brief = read_work_order_brief(work_order_id=TARGET_WO, source_root=REPO, dream_studio_home=home)
    assert brief.get("ok") is True, brief
    assert brief["blocking_milestone_count"] == 1, brief


def test_deleted_predecessor_is_not_a_sequence_blocker(home: Path):
    """A deleted lower-sequence WO in the same milestone must not be a sequence
    predecessor; a genuinely open lower-sequence WO still is."""
    db = home / "state" / "studio.db"
    conn = sqlite3.connect(str(db))
    try:
        _insert_wo(conn, "seq-deleted", MS_LATE, "deleted", seq=10)
        conn.execute(
            "UPDATE business_work_orders SET sequence_order=? WHERE work_order_id=?",
            (20, TARGET_WO),
        )
        conn.commit()
    finally:
        conn.close()

    blockers = _check_sequence_order(TARGET_WO, db)
    assert blockers == [], blockers

    # A created (non-terminal) predecessor must still block.
    conn = sqlite3.connect(str(db))
    try:
        _insert_wo(conn, "seq-open", MS_LATE, "created", seq=5)
        conn.commit()
    finally:
        conn.close()
    blockers = _check_sequence_order(TARGET_WO, db)
    assert [b["work_order_id"] for b in blockers] == ["seq-open"], blockers


def test_terminal_wo_statuses_contract():
    """The single source of truth every lifecycle check reads (start, sequence,
    WO-close signal, milestone close). 'deleted' must be present."""
    assert set(TERMINAL_WO_STATUSES) == {"closed", "cancelled", "deleted"}
