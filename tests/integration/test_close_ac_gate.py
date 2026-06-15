"""Integration tests for executable AC gate on work-order close (WO-AC-EXECUTABLE).

Tests:
  T2 — test_close_blocked_when_any_ac_fails
  T3 — test_close_requires_at_least_one_executable_ac
  T5 — test_close_ac_gate_end_to_end
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-01-01T00:00:00.000000Z"

# Trivial always-passing node used for TEST-CHECK (no recursion risk).
_TRIVIAL_PASS_NODE = "tests/fixtures/trivial_pass_test.py::test_trivial_always_passes"


# ---------------------------------------------------------------------------
# DB / fixture helpers (mirrors test_wo_verify.py conventions)
# ---------------------------------------------------------------------------


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "state" / "studio.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(db_path)
    return db_path


@contextmanager
def _patch_db(db_path: Path):
    fake_paths = MagicMock()
    fake_paths.sqlite_path = db_path
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        yield


def _seed(
    db_path: Path,
    *,
    project_id: str,
    milestone_id: str,
    work_order_id: str,
    wo_type: str = "cleanup",
) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT OR IGNORE INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?)",
        (project_id, "Test", "", "active", NOW, NOW),
    )
    conn.execute(
        "INSERT OR IGNORE INTO business_milestones"
        " (milestone_id, project_id, title, status, order_index, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (milestone_id, project_id, "M1", "active", 1, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description,"
        "  work_order_type, status, sequence_order, created_at, updated_at, last_updated_at)"
        " VALUES (?,?,?,?,?,?,'in_progress',1,?,?,?)",
        (work_order_id, project_id, milestone_id, "Test WO", "desc", wo_type, NOW, NOW, NOW),
    )
    conn.commit()
    conn.close()


def _add_task(
    db_path: Path,
    *,
    work_order_id: str,
    project_id: str,
    title: str,
    desc: str,
    acceptance_criteria: str = "",
) -> str:
    task_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    # Check if acceptance_criteria column exists.
    has_ac = any(
        r[1] == "acceptance_criteria"
        for r in conn.execute("PRAGMA table_info(business_tasks)").fetchall()
    )
    if has_ac:
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, description,"
            "  acceptance_criteria, status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,'complete',?,?)",
            (task_id, work_order_id, project_id, title, desc, acceptance_criteria, NOW, NOW),
        )
    else:
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, description,"
            "  status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,'complete',?,?)",
            (task_id, work_order_id, project_id, title, desc, NOW, NOW),
        )
    conn.commit()
    conn.close()
    return task_id


def _seed_project_row(db_path: Path, project_id: str) -> None:
    """Insert a project row so SQL-CHECK queries can find it."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT OR IGNORE INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?)",
        (project_id, "Test", "", "active", NOW, NOW),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# T2 — close_blocked_when_any_ac_fails
# ---------------------------------------------------------------------------


def test_close_blocked_when_any_ac_fails(tmp_path: Path) -> None:
    """A WO with one failing executable AC cannot close without force.
    With force=True it closes and records the bypass.

    AC: tests/integration/test_close_ac_gate.py::test_close_blocked_when_any_ac_fails
    """
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    work_order_id = str(uuid.uuid4())
    _seed(db_path, project_id=project_id, milestone_id=milestone_id, work_order_id=work_order_id)
    # Add a task with a SQL-CHECK that will FAIL (project-id 'no-such-project' doesn't exist).
    _add_task(
        db_path,
        work_order_id=work_order_id,
        project_id=project_id,
        title="Task with failing SQL check",
        desc="desc",
        acceptance_criteria=(
            "SQL-CHECK: SELECT COUNT(*) FROM business_projects WHERE project_id='no-such-project'"
        ),
    )

    planning_root = tmp_path / "planning"

    # ── 1. Without force → must be blocked ────────────────────────────────
    with _patch_db(db_path):
        from core.work_orders.close import close_work_order

        result_no_force = close_work_order(
            work_order_id=work_order_id,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
            planning_root=planning_root,
            force=False,
        )

    assert (
        result_no_force["ok"] is False
    ), f"Expected close to be blocked with failing AC; got ok=True: {result_no_force}"
    assert "failures" in result_no_force
    ac_failures = [f for f in result_no_force["failures"] if "executable_ac" in f]
    assert (
        ac_failures
    ), f"Expected at least one executable_ac failure; failures={result_no_force['failures']}"

    # ── 2. Verify the WO is still in_progress (not closed) ────────────────
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT status FROM business_work_orders WHERE work_order_id = ?",
        (work_order_id,),
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "in_progress", f"Expected WO to remain in_progress; got {row[0]}"

    # ── 3. With force=True → must close and record bypass ─────────────────
    with _patch_db(db_path):
        from core.work_orders.close import close_work_order as _close_wo

        result_forced = _close_wo(
            work_order_id=work_order_id,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
            planning_root=planning_root,
            force=True,
        )

    assert result_forced["ok"] is True, f"Expected force-close to succeed; got: {result_forced}"
    assert result_forced["forced"] is True
    bypassed = result_forced.get("bypassed_gates", [])
    assert any(
        "executable_ac" in b for b in bypassed
    ), f"Expected bypassed_gates to include AC failures; bypassed={bypassed}"

    # ── 4. WO must now be closed in DB ────────────────────────────────────
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT status FROM business_work_orders WHERE work_order_id = ?",
        (work_order_id,),
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "closed", f"Expected WO to be closed after force=True; got {row[0]}"


# ---------------------------------------------------------------------------
# T3 — close_requires_at_least_one_executable_ac
# ---------------------------------------------------------------------------


def test_close_requires_at_least_one_executable_ac(tmp_path: Path) -> None:
    """A WO with NO executable checks in any task AC cannot close without force.

    AC: tests/integration/test_close_ac_gate.py::test_close_requires_at_least_one_executable_ac
    """
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    work_order_id = str(uuid.uuid4())
    _seed(db_path, project_id=project_id, milestone_id=milestone_id, work_order_id=work_order_id)
    # Task with only free-text acceptance criteria — no *-CHECK lines.
    _add_task(
        db_path,
        work_order_id=work_order_id,
        project_id=project_id,
        title="Task without any checks",
        desc="desc",
        acceptance_criteria="All tests should pass. No CHECK lines here.",
    )

    planning_root = tmp_path / "planning"

    with _patch_db(db_path):
        from core.work_orders.close import close_work_order

        result = close_work_order(
            work_order_id=work_order_id,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
            planning_root=planning_root,
            force=False,
        )

    assert (
        result["ok"] is False
    ), f"Expected close to fail with no executable ACs; got ok=True: {result}"
    assert "failures" in result
    ac_failures = [f for f in result["failures"] if "executable_ac" in f]
    assert ac_failures, f"Expected an executable_ac gate failure; failures={result['failures']}"
    # The message should mention that at least one check is required.
    combined = " ".join(ac_failures)
    assert (
        "at least one" in combined or "no executable" in combined
    ), f"Failure message should mention 'at least one' or 'no executable'; got: {combined}"


# ---------------------------------------------------------------------------
# T5 — end-to-end: passing WO closes; failing WO blocks
# ---------------------------------------------------------------------------


def test_close_ac_gate_end_to_end(tmp_path: Path) -> None:
    """Seed a WO with a passing SQL-CHECK + TEST-CHECK; close without force → ok=True.
    Then seed a second WO with a failing check; close → blocked.

    AC: tests/integration/test_close_ac_gate.py::test_close_ac_gate_end_to_end
    """
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())

    # Seed the project row so SQL-CHECK can find it.
    _seed_project_row(db_path, project_id)

    planning_root = tmp_path / "planning"

    # ── WO-1: passing SQL-CHECK + passing TEST-CHECK ───────────────────────
    wo_id_pass = str(uuid.uuid4())
    _seed(db_path, project_id=project_id, milestone_id=milestone_id, work_order_id=wo_id_pass)
    _add_task(
        db_path,
        work_order_id=wo_id_pass,
        project_id=project_id,
        title="Passing task",
        desc="desc",
        acceptance_criteria=(
            f"SQL-CHECK: SELECT COUNT(*) FROM business_projects WHERE project_id='{project_id}'\n"
            f"TEST-CHECK: {_TRIVIAL_PASS_NODE}"
        ),
    )

    with _patch_db(db_path):
        from core.work_orders.close import close_work_order

        result_pass = close_work_order(
            work_order_id=wo_id_pass,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
            planning_root=planning_root,
            force=False,
        )

    assert result_pass["ok"] is True, f"Expected WO with passing ACs to close; got: {result_pass}"
    assert result_pass["status"] == "closed"

    # ── WO-2: failing SQL-CHECK blocks close ──────────────────────────────
    wo_id_fail = str(uuid.uuid4())
    _seed(db_path, project_id=project_id, milestone_id=milestone_id, work_order_id=wo_id_fail)
    _add_task(
        db_path,
        work_order_id=wo_id_fail,
        project_id=project_id,
        title="Failing task",
        desc="desc",
        acceptance_criteria=(
            "SQL-CHECK: SELECT COUNT(*) FROM business_projects WHERE project_id='impossible-id-xyz'"
        ),
    )

    with _patch_db(db_path):
        result_fail = close_work_order(
            work_order_id=wo_id_fail,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
            planning_root=planning_root,
            force=False,
        )

    assert (
        result_fail["ok"] is False
    ), f"Expected WO with failing AC to be blocked; got ok=True: {result_fail}"
    assert "failures" in result_fail
    assert any(
        "executable_ac" in f for f in result_fail["failures"]
    ), f"Expected executable_ac failure; failures={result_fail['failures']}"
