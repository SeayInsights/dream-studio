"""C1 — Round-trip evals.

Verifies the six core AI-facing function paths work end-to-end against a real
SQLite database (no mocking of DB calls — only the path-resolver is patched so
the test DB is used instead of the operator's live authority).

Evals:
  eval_continue     — get_project_state() surfaces active project + next WO
  eval_start_wo     — start_work_order() writes context.md with skill references
  eval_task_done    — mark_task_done() flips task to complete in DB
  eval_close_wo     — close_work_order() on a gate-free WO reaches complete
  eval_gate_failure — close_work_order() on ui_component without brief → ok=False
  eval_no_cli       — no py -m interfaces.cli.ds pattern in context.md or _ENFORCEMENT_BLOCK
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-05-20T00:00:00+00:00"
PROJECT_ID = "11111111-1111-1111-1111-111111111111"
WO_DOCS_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
WO_UI_ID = "uuuuuuuu-uuuu-uuuu-uuuu-uuuuuuuuuuuu"
TASK_ID = "task-rte-0001"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    target = tmp_path / "studio.db"
    bootstrap_database(target)
    conn = sqlite3.connect(str(target))
    try:
        conn.execute(
            "INSERT INTO business_projects (project_id, name, description, status, created_at, updated_at) VALUES (?, 'Eval Project', '', 'active', ?, ?)",
            (PROJECT_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, NULL, 'Docs WO', '', 'created', 'documentation', ?, ?)",
            (WO_DOCS_ID, PROJECT_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, NULL, 'UI WO', '', 'in_progress', 'ui_component', ?, ?)",
            (WO_UI_ID, PROJECT_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, status, created_at, updated_at)"
            " VALUES (?, ?, ?, 'Write the doc', 'pending', ?, ?)",
            (TASK_ID, WO_DOCS_ID, PROJECT_ID, NOW, NOW),
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
        yield fake


# ── eval_continue ─────────────────────────────────────────────────────────────


def test_eval_continue(patched_paths, tmp_path: Path) -> None:
    """get_project_state() returns active project with a surfaced next work order."""
    from core.projects.queries import get_project_state

    result = get_project_state(
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )

    assert result["ok"] is True
    assert result["projects"], "Expected at least one active project"
    project = result["projects"][0]
    assert project["project_id"] == PROJECT_ID
    assert project["name"] == "Eval Project"
    assert project["next_work_order"] is not None, "Expected a next work order"
    assert project["next_work_order"]["work_order_id"] == WO_DOCS_ID


# ── eval_start_wo ─────────────────────────────────────────────────────────────


def test_eval_start_wo(patched_paths, tmp_path: Path) -> None:
    """start_work_order() writes context.md; content references skills, not CLI commands."""
    from core.work_orders.start import start_work_order

    result = start_work_order(
        work_order_id=WO_DOCS_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )

    assert result["ok"] is True, f"start_work_order failed: {result}"
    context_path = Path(result["context_path"])
    assert context_path.is_file(), "context.md was not created"
    content = context_path.read_text(encoding="utf-8")
    assert "DREAM STUDIO ENFORCEMENT" in content
    assert "ds-workorder:execute" in content
    assert "ds-workorder:close" in content


# ── eval_task_done ────────────────────────────────────────────────────────────


def test_eval_task_done(patched_paths, db_path: Path, tmp_path: Path) -> None:
    """mark_task_done() emits task.completed and returns the complete status.

    Phase 18.2.3: mark_task_done() is event-sourced. The return dict reflects
    the completion state; the DB row is updated asynchronously by TaskProjection.
    """
    from core.work_orders.mutations import mark_task_done

    result = mark_task_done(
        work_order_id=WO_DOCS_ID,
        task_id=TASK_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )

    assert result["ok"] is True, f"mark_task_done failed: {result}"
    assert result["task_id"] == TASK_ID
    assert result["status"] == "complete"
    assert result["tasks_remaining"] == 0
    assert result.get("all_tasks_complete") is True
    # DB row stays pending until TaskProjection applies the task.completed event.


# ── eval_close_wo ─────────────────────────────────────────────────────────────


def test_eval_close_wo(patched_paths, db_path: Path, tmp_path: Path) -> None:
    """close_work_order() on a gate-free WO reaches status=complete."""
    from core.work_orders.close import close_work_order
    from core.work_orders.start import start_work_order

    start_work_order(
        work_order_id=WO_DOCS_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )

    result = close_work_order(
        work_order_id=WO_DOCS_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )

    assert result["ok"] is True, f"close_work_order failed: {result}"
    assert result["status"] == "closed"

    conn = sqlite3.connect(str(db_path))
    try:
        status = conn.execute(
            "SELECT status FROM business_work_orders WHERE work_order_id = ?", (WO_DOCS_ID,)
        ).fetchone()[0]
    finally:
        conn.close()
    assert status == "closed"


# ── eval_gate_failure ─────────────────────────────────────────────────────────


def test_eval_gate_failure(patched_paths, tmp_path: Path) -> None:
    """close_work_order() on ui_component without brief returns ok=False with gate name."""
    from core.work_orders.close import close_work_order

    result = close_work_order(
        work_order_id=WO_UI_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )

    assert result["ok"] is False
    assert "failures" in result
    assert any("design_brief_locked" in f for f in result["failures"])


# ── eval_no_cli ───────────────────────────────────────────────────────────────


def test_eval_no_cli(patched_paths, tmp_path: Path) -> None:
    """Neither context.md nor _ENFORCEMENT_BLOCK contain py -m interfaces.cli.ds."""
    from core.work_orders.start import start_work_order
    from integrations.compiler.claude_code import _ENFORCEMENT_BLOCK

    result = start_work_order(
        work_order_id=WO_DOCS_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )

    assert result["ok"] is True
    content = Path(result["context_path"]).read_text(encoding="utf-8")

    cli_pattern = re.compile(r"py -m interfaces\.cli\.ds")
    assert not cli_pattern.search(content), "context.md must not contain CLI commands"
    assert not cli_pattern.search(
        _ENFORCEMENT_BLOCK
    ), "_ENFORCEMENT_BLOCK must not contain CLI commands"
