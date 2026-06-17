"""Integration tests for close auto-start parity (WO-CLOSE-AUTOSTART-PARITY).

`close_work_order` advertised the next WO via a naive same-milestone, status='created',
sequence-ordered query while auto-starting the WO chosen by the project-wide
`get_next_work_order` ready-set selector. The two could disagree — and the naive
same-milestone pick can even name a WO that `start_work_order` refuses to start (an
earlier milestone is still open). The ready-set selector is authoritative: it respects
cross-milestone ordering, dependencies, and startability.

The fix: auto-start the ready-set pick AND advertise that same WO in
`next_work_order`/`next_block`, so the WO we tell the operator is next is exactly the
one we auto-start.

Tests:
  T1 — test_autostart_matches_next_work_order
  T2 — test_end_to_end
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from unittest.mock import MagicMock, patch

from core.config.sqlite_bootstrap import bootstrap_database

NOW = "2026-01-01T00:00:00+00:00"


@contextmanager
def _patch_close_runtime(db_path: Path):
    fake = MagicMock()
    fake.sqlite_path = db_path
    with (
        patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake),
        patch("core.projections.runner.sync_tick", new=MagicMock()),
    ):
        yield


def _make_db(tmp_path: Path) -> Path:
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(db)
    return db


def _seed_project(db_path: Path) -> str:
    project_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO business_projects (project_id, name, description, status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?)",
            (project_id, "Test", "", "active", NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return project_id


def _seed_milestone(db_path: Path, project_id: str, *, order_index: int) -> str:
    milestone_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO business_milestones (milestone_id, project_id, title, status, order_index, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (milestone_id, project_id, f"M{order_index}", "active", order_index, NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return milestone_id


def _seed_wo(
    db_path: Path,
    *,
    project_id: str,
    milestone_id: str,
    status: str,
    sequence_order: int,
    with_passing_task: bool = False,
) -> str:
    wo = str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    try:
        # infrastructure type has post_build_gate='independent_review' in a fresh
        # bootstrap, which is what triggers the inline auto-verify + auto-start path
        # under test (the 'cleanup' type is not seeded in test DBs).
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, work_order_type,"
            "  status, sequence_order, created_at, updated_at, last_updated_at)"
            " VALUES (?,?,?,?,?,'infrastructure',?,?,?,?,?)",
            (
                wo,
                project_id,
                milestone_id,
                f"WO {wo[:8]}",
                "d",
                status,
                sequence_order,
                NOW,
                NOW,
                NOW,
            ),
        )
        if with_passing_task:
            conn.execute(
                "INSERT INTO business_tasks"
                " (task_id, work_order_id, project_id, title, description, acceptance_criteria,"
                "  status, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?, 'complete', ?, ?)",
                (str(uuid.uuid4()), wo, project_id, "T1", "d", "SQL-CHECK: SELECT 1", NOW, NOW),
            )
        conn.commit()
    finally:
        conn.close()
    return wo


# ---------------------------------------------------------------------------
# T1 — auto_started matches the advertised next_work_order
# ---------------------------------------------------------------------------


def test_autostart_matches_next_work_order(tmp_path: Path) -> None:
    """The WO advertised as next_work_order is exactly the WO auto-started — the
    startable project-wide ready-set pick (wo_c). A naive same-milestone selector would
    have advertised wo_a, which start_work_order refuses because an earlier milestone is
    still open; the fix makes both fields agree on the startable next.

    AC: tests/integration/test_close_autostart_parity.py::test_autostart_matches_next_work_order
    """
    from core.work_orders.close import close_work_order

    db = _make_db(tmp_path)
    planning_root = tmp_path / ".planning"
    project = _seed_project(db)
    # Earlier milestone with a ready WO the project-wide selector would rank first.
    m1 = _seed_milestone(db, project, order_index=0)
    wo_c = _seed_wo(db, project_id=project, milestone_id=m1, status="created", sequence_order=10)
    # Current milestone: the WO we close + a sequence-correct same-milestone next.
    m2 = _seed_milestone(db, project, order_index=1)
    wo_close = _seed_wo(
        db,
        project_id=project,
        milestone_id=m2,
        status="in_progress",
        sequence_order=10,
        with_passing_task=True,
    )
    wo_a = _seed_wo(db, project_id=project, milestone_id=m2, status="created", sequence_order=20)

    with _patch_close_runtime(db):
        result = close_work_order(
            work_order_id=wo_close,
            source_root=tmp_path,
            dream_studio_home=tmp_path,
            planning_root=planning_root,
            force=False,
        )

    assert result["ok"] is True, f"expected clean close; got {result}"
    # Parity: advertised next == auto-started, and it's the startable project-wide pick
    # (wo_c), NOT the same-milestone wo_a that start_work_order would refuse.
    assert result["auto_started"]["work_order_id"] == result["next_work_order"]["work_order_id"]
    assert result["auto_started"]["work_order_id"] == wo_c
    assert result["auto_started"]["work_order_id"] != wo_a
    assert "auto_start_error" not in result


# ---------------------------------------------------------------------------
# T2 — fallback to the project-wide selector when the milestone is exhausted
# ---------------------------------------------------------------------------


def test_end_to_end(tmp_path: Path) -> None:
    """When the closed WO's milestone has no further open WO, auto-start falls back
    to the project-wide next WO (an earlier milestone's ready WO).

    AC: tests/integration/test_close_autostart_parity.py::test_end_to_end
    """
    from core.work_orders.close import close_work_order

    db = _make_db(tmp_path)
    planning_root = tmp_path / ".planning"
    project = _seed_project(db)
    m1 = _seed_milestone(db, project, order_index=0)
    wo_c = _seed_wo(db, project_id=project, milestone_id=m1, status="created", sequence_order=10)
    # Current milestone holds ONLY the WO we close — no further same-milestone WO.
    m2 = _seed_milestone(db, project, order_index=1)
    wo_close = _seed_wo(
        db,
        project_id=project,
        milestone_id=m2,
        status="in_progress",
        sequence_order=10,
        with_passing_task=True,
    )

    with _patch_close_runtime(db):
        result = close_work_order(
            work_order_id=wo_close,
            source_root=tmp_path,
            dream_studio_home=tmp_path,
            planning_root=planning_root,
            force=False,
        )

    assert result["ok"] is True, f"expected clean close; got {result}"
    # The closed WO's milestone (m2) is exhausted, and the project-wide next is wo_c in
    # the earlier milestone. Parity holds: advertised next == auto-started == wo_c.
    assert result["auto_started"]["work_order_id"] == wo_c
    assert result["next_work_order"]["work_order_id"] == wo_c
    assert result["auto_started"]["work_order_id"] == result["next_work_order"]["work_order_id"]
