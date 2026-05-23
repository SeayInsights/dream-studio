"""Substrate policy H4: read-after-write correctness under projection lag.

These tests verify the canonical-events fallback in close_milestone.
The setup deliberately mirrors the real failure mode:
  - business_work_orders shows stale state (projection not yet applied)
  - business_canonical_events holds the authoritative closed event

Each test writes events directly to business_canonical_events and does NOT
run the projection runner.  The function under test must handle the lag.

As new projections land (18.2.3+), add the corresponding writer→reader
chains to this file following the same pattern.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_PROJECT_ID = "proj-h4-test-00000000"
_MILESTONE_ID = "ms-h4-test-000000000"
_WO_CLOSED = "wo-h4-stale-000000000"
_WO_GENUINELY_OPEN = "wo-h4-open-000000000"
_NOW = "2026-05-23T12:00:00+00:00"


@pytest.fixture()
def db_home(tmp_path, monkeypatch):
    from core.config.sqlite_bootstrap import bootstrap_database

    db_path = tmp_path / "state" / "studio.db"
    bootstrap_database(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            "INSERT INTO business_milestones"
            " (milestone_id, project_id, title, status, created_at, updated_at)"
            " VALUES (?, ?, 'H4 Test Milestone', 'active', ?, ?)",
            (_MILESTONE_ID, _PROJECT_ID, _NOW, _NOW),
        )
        # WO that is canonically closed but still in_progress in the projection.
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, status,"
            "  work_order_type, created_at, last_updated_at)"
            " VALUES (?, ?, ?, 'Stale WO', 'in_progress',"
            "  'api_endpoint', ?, ?)",
            (_WO_CLOSED, _PROJECT_ID, _MILESTONE_ID, _NOW, _NOW),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    return tmp_path


def _insert_closed_event(db_home: Path, work_order_id: str) -> None:
    """Write a work_order.closed canonical event without running the projection."""
    db_path = db_home / "state" / "studio.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO business_canonical_events"
            " (event_id, event_type, event_timestamp, work_order_id,"
            "  milestone_id, project_id, trace, payload)"
            " VALUES (?, 'work_order.closed', ?, ?, ?, ?, '{}', ?)",
            (
                str(uuid.uuid4()),
                _NOW,
                work_order_id,
                _MILESTONE_ID,
                _PROJECT_ID,
                json.dumps(
                    {
                        "work_order_id": work_order_id,
                        "title": "Stale WO",
                        "project_id": _PROJECT_ID,
                        "forced": False,
                    }
                ),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _call_close_milestone(db_home: Path, force: bool = True) -> dict:
    from core.milestones.close import close_milestone

    return close_milestone(
        milestone_id=_MILESTONE_ID,
        force=force,
        source_root=REPO_ROOT,
        dream_studio_home=db_home,
        planning_root=db_home / ".planning",
    )


class TestCloseMilestoneH4:
    def test_fails_when_wo_in_projection_and_no_canonical_event(self, db_home):
        """Baseline: stale projection with no canonical event → milestone close is correctly blocked."""
        result = _call_close_milestone(db_home)
        assert result["ok"] is False
        assert "open work orders remain" in result["error"]
        open_ids = [r["work_order_id"] for r in result["open_work_orders"]]
        assert _WO_CLOSED in open_ids

    def test_passes_when_wo_stale_in_projection_but_closed_in_canonical(self, db_home):
        """H4-2 fix: canonical-events fallback allows milestone close despite projection lag."""
        _insert_closed_event(db_home, _WO_CLOSED)
        result = _call_close_milestone(db_home, force=True)
        assert result["ok"] is True, f"Expected ok=True but got: {result}"
        assert result["milestone_id"] == _MILESTONE_ID

    def test_partially_stale_projection_blocks_on_genuinely_open_wo(self, db_home):
        """Fallback only removes canonically-closed WOs; genuinely open WOs still block."""
        db_path = db_home / "state" / "studio.db"
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "INSERT INTO business_work_orders"
                " (work_order_id, project_id, milestone_id, title, status,"
                "  work_order_type, created_at, last_updated_at)"
                " VALUES (?, ?, ?, 'Genuinely Open WO', 'in_progress',"
                "  'api_endpoint', ?, ?)",
                (_WO_GENUINELY_OPEN, _PROJECT_ID, _MILESTONE_ID, _NOW, _NOW),
            )
            conn.commit()
        finally:
            conn.close()

        _insert_closed_event(db_home, _WO_CLOSED)

        result = _call_close_milestone(db_home)
        assert result["ok"] is False
        open_ids = [r["work_order_id"] for r in result["open_work_orders"]]
        assert _WO_GENUINELY_OPEN in open_ids
        assert _WO_CLOSED not in open_ids
