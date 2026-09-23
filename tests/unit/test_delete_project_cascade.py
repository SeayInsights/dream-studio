"""``delete_project``: the cascade, and the preview that has to come first.

Originally A6.3, which covered both the ds-project:manage mode's shape and the
``delete_project`` function the mode wrapped. The pack was dissolved -- every branch of
that mode was already `ds project list|set-active|deactivate|delete` -- and its seven
shape tests went with it. These four cover the function, which nothing about the
dissolution changed and which enforces
``a-cascade-delete-previews-what-it-destroys`` in canonical/rules.yml.

The unconfirmed call is the safe default, so a caller that forgets the flag is handed the
dependent counts rather than a deletion; the refusal test asserts the project row is still
there afterwards, because a refusal that had already written would be worse than none.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]
PACK_NAME = "ds-project"
MODE_NAME = "manage"
NOW = "2026-05-20T00:00:00+00:00"
PROJECT_ID = "p-manage-ext-0001"
OTHER_PROJECT_ID = "p-manage-ext-other-0001"


# ── Skill pack registration ───────────────────────────────────────────────────


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    target = tmp_path / "studio.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(target)
    conn = sqlite3.connect(str(target))
    try:
        conn.execute(
            "INSERT INTO business_projects"
            " (project_id, name, description, status, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (PROJECT_ID, "Manage Ext Project", "", "active", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_milestones"
            " (milestone_id, project_id, title, description, status, order_index,"
            " created_at, updated_at)"
            " VALUES (?, ?, ?, '', 'pending', 0, ?, ?)",
            ("ms-manage-1", PROJECT_ID, "First", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, '', 'created', 'api_endpoint', ?, ?)",
            ("wo-manage-1", PROJECT_ID, "ms-manage-1", "WO", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, project_id, work_order_id, title, description, status,"
            " created_at, updated_at)"
            " VALUES (?, ?, ?, ?, '', 'pending', ?, ?)",
            ("task-manage-1", PROJECT_ID, "wo-manage-1", "Task", NOW, NOW),
        )
        # A second project with no dependents — used to test the no-confirm
        # cascade path (deletes cleanly because there's nothing to cascade).
        conn.execute(
            "INSERT INTO business_projects"
            " (project_id, name, description, status, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (OTHER_PROJECT_ID, "Other", "", "paused", NOW, NOW),
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


def test_delete_project_returns_error_for_unknown_project(patched_paths, tmp_path: Path) -> None:
    from core.projects.mutations import delete_project

    result = delete_project(
        project_id="does-not-exist",
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert result["ok"] is False
    assert "not found" in result["error"]


def test_delete_project_refuses_when_dependents_and_no_confirm(
    patched_paths, db_path: Path, tmp_path: Path
) -> None:
    from core.projects.mutations import delete_project

    result = delete_project(
        project_id=PROJECT_ID,
        confirm=False,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert result["ok"] is False
    assert "Pass confirm=True" in result["error"]
    assert result["task_count"] == 1
    assert result["work_order_count"] == 1
    assert result["milestone_count"] == 1

    # And the row is still there.
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT project_id FROM business_projects WHERE project_id = ?", (PROJECT_ID,)
        ).fetchone()
    assert row is not None


def test_delete_project_cascades_with_confirm(patched_paths, db_path: Path, tmp_path: Path) -> None:
    from core.projects.mutations import delete_project

    result = delete_project(
        project_id=PROJECT_ID,
        confirm=True,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert result["ok"] is True
    assert result["deleted"]["tasks"] == 1
    assert result["deleted"]["work_orders"] == 1
    assert result["deleted"]["milestones"] == 1
    # Rows remain in place — ProjectProjection applies soft-deletes asynchronously
    # from the cascade events emitted above. The mutation's job ends at event emission.


def test_delete_project_no_dependents_succeeds_without_confirm(
    patched_paths, db_path: Path, tmp_path: Path
) -> None:
    """A project with no tasks/WOs/milestones can be deleted without
    confirm=True — there's nothing to cascade."""
    from core.projects.mutations import delete_project

    result = delete_project(
        project_id=OTHER_PROJECT_ID,
        confirm=False,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert result["ok"] is True
    assert result["deleted"] == {"tasks": 0, "work_orders": 0, "milestones": 0}
