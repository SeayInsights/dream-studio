"""Tests for sequence-order guard in `core.work_orders.start`.

Covers:
- `_check_sequence_order` returns empty list when no blocker exists
- `_check_sequence_order` returns blockers when lower-seq WOs are not closed
- `start_work_order` emits soft warning (sequence_warning in result) when blockers exist
- `start_work_order` aborts with ok=False when in_sequence=True and blockers exist
- No false positive when all lower-seq WOs are closed
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders.start import _check_sequence_order

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-05-20T00:00:00+00:00"
PROJECT_ID = "p-seq-test-0001"
MILESTONE_ID = "ms-seq-test-0001"
WO_FIRST = "wo-seq-first-000000000000001"
WO_SECOND = "wo-seq-second-00000000000002"
WO_THIRD = "wo-seq-third-000000000000003"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    target = tmp_path / "studio.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(target)
    conn = sqlite3.connect(str(target))
    try:
        conn.execute(
            "INSERT INTO business_projects (project_id, name, description, status, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (PROJECT_ID, "Seq Test Project", "", "active", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_milestones"
            " (milestone_id, project_id, title, description, status, order_index,"
            " created_at, updated_at)"
            " VALUES (?, ?, ?, '', 'pending', 0, ?, ?)",
            (MILESTONE_ID, PROJECT_ID, "Milestone 1", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, sequence_order, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, '', 'created', 'documentation', 10, ?, ?)",
            (WO_FIRST, PROJECT_ID, MILESTONE_ID, "First WO", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, sequence_order, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, '', 'created', 'documentation', 20, ?, ?)",
            (WO_SECOND, PROJECT_ID, MILESTONE_ID, "Second WO", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, sequence_order, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, '', 'created', 'documentation', 30, ?, ?)",
            (WO_THIRD, PROJECT_ID, MILESTONE_ID, "Third WO", NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return target


@pytest.fixture
def patched_paths(db_path: Path, tmp_path: Path):
    fake = MagicMock()
    fake.sqlite_path = db_path
    fake.source_root = REPO_ROOT
    fake.dream_studio_home = tmp_path
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake):
        yield db_path


class TestCheckSequenceOrder:
    def test_no_blockers_when_first_in_sequence(self, db_path):
        result = _check_sequence_order(WO_FIRST, db_path)
        assert result == []

    def test_returns_blockers_for_second_wo(self, db_path):
        result = _check_sequence_order(WO_SECOND, db_path)
        assert len(result) == 1
        assert result[0]["work_order_id"] == WO_FIRST
        assert result[0]["sequence_order"] == 10

    def test_returns_all_blockers_for_third_wo(self, db_path):
        result = _check_sequence_order(WO_THIRD, db_path)
        assert len(result) == 2
        ids = {r["work_order_id"] for r in result}
        assert WO_FIRST in ids
        assert WO_SECOND in ids

    def test_no_blockers_when_lower_seq_wo_is_closed(self, db_path):
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "UPDATE business_work_orders SET status = 'closed' WHERE work_order_id = ?",
            (WO_FIRST,),
        )
        conn.commit()
        conn.close()
        result = _check_sequence_order(WO_SECOND, db_path)
        assert result == []

    def test_no_blockers_when_wo_has_no_sequence_order(self, db_path):
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "UPDATE business_work_orders SET sequence_order = NULL WHERE work_order_id = ?",
            (WO_SECOND,),
        )
        conn.commit()
        conn.close()
        result = _check_sequence_order(WO_SECOND, db_path)
        assert result == []

    def test_returns_empty_for_unknown_wo(self, db_path):
        result = _check_sequence_order("nonexistent-wo-id", db_path)
        assert result == []


class TestStartWorkOrderSequenceGuard:
    def test_soft_warning_when_blockers_exist(self, patched_paths, tmp_path):
        from core.work_orders.start import start_work_order

        # Don't patch _connect — _check_sequence_order must read from the real tmp db.
        # Only stub out side effects that would fail outside the db fixture.
        with (
            patch("core.work_orders.start._check_preflight_gate", return_value=None),
            patch(
                "core.work_orders.start.write_work_order_context", return_value=tmp_path / "ctx.md"
            ),
            patch("core.work_orders.start._get_pending_audits_for_project", return_value=[]),
            patch("spool.writer.write_event"),
        ):
            brief = {
                "ok": True,
                "work_order_id": WO_SECOND,
                "title": "Second WO",
                "status": "created",
                "type_id": "documentation",
                "label": "Documentation",
                "pre_gate": None,
                "build_exec": None,
                "post_gate": None,
                "workflow_template": None,
                "precondition_skill": None,
                "milestone_id": MILESTONE_ID,
                "milestone_title": "Milestone 1",
                "project_id": PROJECT_ID,
                "project_name": "Seq Test Project",
                "marker_project_id": None,
                "pending_tasks": [],
                "brief_locked": None,
                "brief_warning": False,
                "gotchas": [],
                "blocking_milestone_count": 0,
            }
            result = start_work_order(
                work_order_id=WO_SECOND,
                source_root=REPO_ROOT,
                brief_data=brief,
                in_sequence=False,
            )
        assert result.get("ok") is True
        assert "sequence_warning" in result
        assert "Proceeding." in result["sequence_warning"]
        assert len(result.get("sequence_blockers", [])) == 1

    def test_aborts_with_in_sequence_flag(self, patched_paths, tmp_path):
        from core.work_orders.start import start_work_order

        brief = {
            "ok": True,
            "work_order_id": WO_SECOND,
            "title": "Second WO",
            "status": "created",
            "type_id": "documentation",
            "label": "Documentation",
            "pre_gate": None,
            "build_exec": None,
            "post_gate": None,
            "workflow_template": None,
            "precondition_skill": None,
            "milestone_id": MILESTONE_ID,
            "milestone_title": "Milestone 1",
            "project_id": PROJECT_ID,
            "project_name": "Seq Test Project",
            "marker_project_id": None,
            "pending_tasks": [],
            "brief_locked": None,
            "brief_warning": False,
            "gotchas": [],
            "blocking_milestone_count": 0,
        }
        result = start_work_order(
            work_order_id=WO_SECOND,
            source_root=REPO_ROOT,
            brief_data=brief,
            in_sequence=True,
        )
        assert result.get("ok") is False
        assert "sequence_blockers" in result
        assert len(result["sequence_blockers"]) == 1

    def test_no_warning_when_in_sequence_and_first(self, patched_paths, tmp_path):
        from core.work_orders.start import start_work_order

        with (
            patch("core.work_orders.start._check_preflight_gate", return_value=None),
            patch(
                "core.work_orders.start.write_work_order_context", return_value=tmp_path / "ctx.md"
            ),
            patch("core.work_orders.start._get_pending_audits_for_project", return_value=[]),
            patch("spool.writer.write_event"),
        ):
            brief = {
                "ok": True,
                "work_order_id": WO_FIRST,
                "title": "First WO",
                "status": "created",
                "type_id": "documentation",
                "label": "Documentation",
                "pre_gate": None,
                "build_exec": None,
                "post_gate": None,
                "workflow_template": None,
                "precondition_skill": None,
                "milestone_id": MILESTONE_ID,
                "milestone_title": "Milestone 1",
                "project_id": PROJECT_ID,
                "project_name": "Seq Test Project",
                "marker_project_id": None,
                "pending_tasks": [],
                "brief_locked": None,
                "brief_warning": False,
                "gotchas": [],
                "blocking_milestone_count": 0,
            }
            result = start_work_order(
                work_order_id=WO_FIRST,
                source_root=REPO_ROOT,
                brief_data=brief,
                in_sequence=True,
            )
        assert result.get("ok") is True
        assert "sequence_warning" not in result
        assert "sequence_blockers" not in result
