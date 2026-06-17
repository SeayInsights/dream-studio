"""Integration tests for the tasks_done close gate (WO-TASKS-DONE-ENFORCE).

A work order cannot be closed while any of its tasks is still pending — no 0/N or
partial closes ("NOTHING LEFT HANGING"). Enforcement lives in the single shared
``close_work_order`` chokepoint, so both the CLI close path and the autonomous
execute-work-orders loop inherit it identically.

Tests:
  T1 — test_close_blocked_with_pending_tasks
  T3 — test_loop_and_cli_enforce_tasks_done
  T4 — test_end_to_end

``sync_tick`` is patched to a no-op throughout: these tests seed task statuses
directly into the temp authority DB, so the real projection cycle (which resolves
its own DB from the environment) must not run and must not touch any live DB.
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from unittest.mock import MagicMock, patch

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-01-01T00:00:00.000000Z"

# A passing SQL-CHECK template — satisfies the always-on executable-AC gate so the
# only remaining close blocker under test is tasks_done.
_PASS_AC = "SQL-CHECK: SELECT COUNT(*) FROM business_projects WHERE project_id='{pid}'"


# ---------------------------------------------------------------------------
# Helpers (mirror tests/integration/test_close_ac_gate.py conventions)
# ---------------------------------------------------------------------------


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "state" / "studio.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(db_path)
    return db_path


@contextmanager
def _patch_close_runtime(db_path: Path):
    """Point the close path at the temp DB and neutralize the real projection tick."""
    fake_paths = MagicMock()
    fake_paths.sqlite_path = db_path
    with (
        patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths),
        patch("core.projections.runner.sync_tick", new=MagicMock()),
    ):
        yield


def _seed(db_path: Path, *, project_id: str, milestone_id: str, work_order_id: str) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
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
            " VALUES (?,?,?,?,?,'cleanup','in_progress',1,?,?,?)",
            (work_order_id, project_id, milestone_id, "Test WO", "desc", NOW, NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()


def _add_task(
    db_path: Path,
    *,
    work_order_id: str,
    project_id: str,
    title: str,
    status: str,
    acceptance_criteria: str = "",
) -> str:
    task_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, description,"
            "  acceptance_criteria, status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (
                task_id,
                work_order_id,
                project_id,
                title,
                "desc",
                acceptance_criteria,
                status,
                NOW,
                NOW,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return task_id


def _wo_status(db_path: Path, work_order_id: str) -> str:
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(
            "SELECT status FROM business_work_orders WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()[0]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# T1 — close blocked with pending tasks
# ---------------------------------------------------------------------------


def test_close_blocked_with_pending_tasks(tmp_path: Path) -> None:
    """A WO with a pending task cannot close without force; force closes and records it.

    AC: tests/integration/test_tasks_done_gate.py::test_close_blocked_with_pending_tasks
    """
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    work_order_id = str(uuid.uuid4())
    _seed(db_path, project_id=project_id, milestone_id=milestone_id, work_order_id=work_order_id)
    # One done task, one still pending — a classic partial-completion state.
    _add_task(
        db_path,
        work_order_id=work_order_id,
        project_id=project_id,
        title="Done task",
        status="complete",
        acceptance_criteria=_PASS_AC.format(pid=project_id),
    )
    _add_task(
        db_path,
        work_order_id=work_order_id,
        project_id=project_id,
        title="Still pending task",
        status="pending",
    )
    planning_root = tmp_path / "planning"

    # ── Without force → blocked by tasks_done ─────────────────────────────
    with _patch_close_runtime(db_path):
        from core.work_orders.close import close_work_order

        result_no_force = close_work_order(
            work_order_id=work_order_id,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
            planning_root=planning_root,
            force=False,
        )

    assert result_no_force["ok"] is False, f"Expected close to be blocked; got: {result_no_force}"
    tasks_done_failures = [f for f in result_no_force["failures"] if f.startswith("tasks_done")]
    assert (
        tasks_done_failures
    ), f"Expected a tasks_done failure; failures={result_no_force['failures']}"
    # Names the offending task and reports a count.
    assert "Still pending task" in tasks_done_failures[0]
    assert _wo_status(db_path, work_order_id) == "in_progress"

    # ── With force=True → closes and records the bypass ───────────────────
    with _patch_close_runtime(db_path):
        from core.work_orders.close import close_work_order as _close

        result_forced = _close(
            work_order_id=work_order_id,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
            planning_root=planning_root,
            force=True,
        )

    assert result_forced["ok"] is True, f"Expected force-close to succeed; got: {result_forced}"
    assert result_forced["forced"] is True
    assert any(
        b.startswith("tasks_done") for b in result_forced.get("bypassed_gates", [])
    ), f"Expected tasks_done in bypassed_gates; got {result_forced.get('bypassed_gates')}"
    assert _wo_status(db_path, work_order_id) == "closed"


# ---------------------------------------------------------------------------
# T3 — both the CLI path and the autonomous loop enforce tasks_done
# ---------------------------------------------------------------------------


def test_loop_and_cli_enforce_tasks_done(tmp_path: Path) -> None:
    """The CLI wrapper refuses (exit 1) on pending tasks, and the autonomous loop
    closes through the same gated CLI command — so neither path can leave tasks hanging.

    AC: tests/integration/test_tasks_done_gate.py::test_loop_and_cli_enforce_tasks_done
    """
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    work_order_id = str(uuid.uuid4())
    _seed(db_path, project_id=project_id, milestone_id=milestone_id, work_order_id=work_order_id)
    _add_task(
        db_path,
        work_order_id=work_order_id,
        project_id=project_id,
        title="Pending task",
        status="pending",
        acceptance_criteria=_PASS_AC.format(pid=project_id),
    )
    planning_root = tmp_path / "planning"

    # ── CLI path: the operator-facing wrapper returns a non-zero exit code ──
    with _patch_close_runtime(db_path):
        from interfaces.cli.ds import _work_order_close

        exit_code = _work_order_close(
            work_order_id=work_order_id,
            force=False,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
            planning_root=planning_root,
        )
    assert exit_code == 1, "CLI close wrapper must fail (exit 1) when a task is pending"
    assert _wo_status(db_path, work_order_id) == "in_progress"

    # ── Loop path: the autonomous execute-work-orders workflow closes via the
    # same gated CLI command (`ds work-order close`) rather than a raw status
    # write — so the loop inherits the identical tasks_done enforcement. ──────
    wf = (REPO_ROOT / "canonical" / "workflows" / "execute-work-orders.yaml").read_text(
        encoding="utf-8"
    )
    assert "work-order close" in wf, (
        "The autonomous loop must close work orders through the gated CLI command, "
        "not a path that bypasses close_work_order."
    )
    # And it must never force-close autonomously.
    assert "never allowed autonomously" in wf or "do NOT --force" in wf


# ---------------------------------------------------------------------------
# T4 — end-to-end: blocked while pending, closes once every task is done
# ---------------------------------------------------------------------------


def test_end_to_end(tmp_path: Path) -> None:
    """Full gate lifecycle: a WO blocks while a task is pending, then closes cleanly
    once that task is marked done (read model shows 'complete').

    AC: tests/integration/test_tasks_done_gate.py::test_end_to_end
    """
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    work_order_id = str(uuid.uuid4())
    _seed(db_path, project_id=project_id, milestone_id=milestone_id, work_order_id=work_order_id)
    task_id = _add_task(
        db_path,
        work_order_id=work_order_id,
        project_id=project_id,
        title="The only task",
        status="pending",
        acceptance_criteria=_PASS_AC.format(pid=project_id),
    )
    planning_root = tmp_path / "planning"

    # ── 1. Pending → close blocked ────────────────────────────────────────
    with _patch_close_runtime(db_path):
        from core.work_orders.close import close_work_order

        blocked = close_work_order(
            work_order_id=work_order_id,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
            planning_root=planning_root,
            force=False,
        )
    assert blocked["ok"] is False
    assert any(f.startswith("tasks_done") for f in blocked["failures"])
    assert _wo_status(db_path, work_order_id) == "in_progress"

    # ── 2. Task completed (the state mark_task_done's projection materializes) ─
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("UPDATE business_tasks SET status = 'complete' WHERE task_id = ?", (task_id,))
        conn.commit()
    finally:
        conn.close()

    # ── 3. All tasks done → close succeeds without force ──────────────────
    with _patch_close_runtime(db_path):
        from core.work_orders.close import close_work_order as _close

        ok = _close(
            work_order_id=work_order_id,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
            planning_root=planning_root,
            force=False,
        )
    assert ok["ok"] is True, f"Expected clean close once all tasks are done; got: {ok}"
    assert ok["status"] == "closed"
    assert _wo_status(db_path, work_order_id) == "closed"
