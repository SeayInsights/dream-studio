"""Direct-call tests for the A2.3 split of `_project_start` into the
`start_project` composer in `core.projects.start`."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-05-20T00:00:00+00:00"
PROJECT_ID = "p-start-ext-0001"
OTHER_PROJECT_ID = "p-start-ext-other-active"
MILESTONE_ID = "ms-start-ext-0001"
WO_OPEN_ID = "wo-start-ext-open-01"
WO_UI_ID = "wo-start-ext-ui-no-brief-01"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    target = tmp_path / "studio.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(target)
    conn = sqlite3.connect(str(target))
    try:
        # Two projects — the target plus one already-active project so we can
        # prove `start_project` demotes it via `set_active_project`.
        conn.execute(
            "INSERT INTO business_projects (project_id, name, description, status, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (OTHER_PROJECT_ID, "Other Active", "", "active", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_projects (project_id, name, description, status, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (PROJECT_ID, "Test Project", "", "paused", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_milestones"
            " (milestone_id, project_id, title, description, status, order_index,"
            " created_at, updated_at)"
            " VALUES (?, ?, ?, '', 'pending', 0, ?, ?)",
            (MILESTONE_ID, PROJECT_ID, "Foundation", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, '', 'created', 'api_endpoint', ?, ?)",
            (WO_OPEN_ID, PROJECT_ID, MILESTONE_ID, "Backend WO", NOW, NOW),
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


# ── start_project: error paths ────────────────────────────────────────────────


def test_start_project_returns_error_for_unknown_project(patched_paths, tmp_path: Path) -> None:
    from core.projects.start import start_project

    result = start_project(
        project_id="does-not-exist",
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    assert result["ok"] is False
    assert "not found" in result["error"]


# ── start_project: success paths ──────────────────────────────────────────────


def test_start_project_returns_compound_dict_on_success(patched_paths, tmp_path: Path) -> None:
    from core.projects.start import start_project

    result = start_project(
        project_id=PROJECT_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    assert result["ok"] is True
    assert result["project_id"] == PROJECT_ID
    assert result["project_name"] == "Test Project"
    assert result["project_status"] == "active"
    assert result["next_work_order"]["work_order_id"] == WO_OPEN_ID
    assert result["work_order_start"]["ok"] is True
    # WO-FILESDB-C2: context lives in the authority (context_path None), not on disk.
    assert result["context_in_authority"] is True
    assert result["context_path"] is None
    assert isinstance(result["tasks_count"], int)


def test_start_project_demotes_previously_active_project(
    patched_paths, db_path: Path, tmp_path: Path
) -> None:
    from core.projects.start import start_project

    start_project(
        project_id=PROJECT_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    with sqlite3.connect(str(db_path)) as conn:
        statuses = {
            row[0]: row[1]
            for row in conn.execute("SELECT project_id, status FROM business_projects").fetchall()
        }
    assert statuses[PROJECT_ID] == "active"
    assert statuses[OTHER_PROJECT_ID] == "paused"


def test_start_project_marks_target_work_order_in_progress(
    patched_paths, db_path: Path, tmp_path: Path
) -> None:
    from core.projects.start import start_project

    start_project(
        project_id=PROJECT_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    with sqlite3.connect(str(db_path)) as conn:
        status = conn.execute(
            "SELECT status FROM business_work_orders WHERE work_order_id = ?", (WO_OPEN_ID,)
        ).fetchone()[0]
    assert status == "in_progress"


def test_start_project_stores_context_in_authority(
    patched_paths, db_path: Path, tmp_path: Path
) -> None:
    """WO-FILESDB-C2: context is stored in business_work_order_artifacts, not on disk."""
    from core.projects.start import start_project
    from core.work_orders.artifacts import get_wo_artifact

    planning_root = tmp_path / ".planning"
    result = start_project(
        project_id=PROJECT_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=planning_root,
    )
    # No context.md written to disk.
    assert list(planning_root.rglob("context.md")) == []
    assert result["context_path"] is None
    assert result["context_in_authority"] is True
    # The rendered context lives in the authority.
    stored = get_wo_artifact(WO_OPEN_ID, "context", db_path=db_path)
    assert stored is not None
    assert "# Work Order:" in stored


# ── start_project: no open work orders ────────────────────────────────────────


def test_start_project_signals_no_open_work_orders(
    patched_paths, db_path: Path, tmp_path: Path
) -> None:
    from core.projects.start import start_project

    # Mark the only open WO as complete so the project has nothing to start.
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE business_work_orders SET status = 'closed' WHERE work_order_id = ?",
        (WO_OPEN_ID,),
    )
    conn.commit()
    conn.close()

    result = start_project(
        project_id=PROJECT_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    assert result["ok"] is True
    assert result.get("no_open_work_orders") is True
    assert result["project_status"] == "active"
    assert "next_work_order" not in result


def test_start_project_activates_project_even_when_no_open_wos(
    patched_paths, db_path: Path, tmp_path: Path
) -> None:
    from core.projects.start import start_project

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE business_work_orders SET status = 'closed' WHERE work_order_id = ?",
        (WO_OPEN_ID,),
    )
    conn.commit()
    conn.close()

    start_project(
        project_id=PROJECT_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    with sqlite3.connect(str(db_path)) as conn:
        status = conn.execute(
            "SELECT status FROM business_projects WHERE project_id = ?", (PROJECT_ID,)
        ).fetchone()[0]
    assert status == "active"


# ── start_project: propagates start_work_order failure ───────────────────────


def test_start_project_propagates_brief_block_for_ui_wo(
    patched_paths, db_path: Path, tmp_path: Path
) -> None:
    """If start_work_order returns ok=False (UI WO needs a brief), pass it through."""
    from core.projects.start import start_project

    # Replace the open WO with a UI-typed one — start_work_order will return
    # ok=False with requires_brief_confirmation=True unless accept_no_brief.
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE business_work_orders SET work_order_type = 'ui_page' WHERE work_order_id = ?",
        (WO_OPEN_ID,),
    )
    conn.commit()
    conn.close()

    result = start_project(
        project_id=PROJECT_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
        accept_no_brief=False,
    )
    assert result["ok"] is False
    assert result.get("requires_brief_confirmation") is True


def test_start_project_accept_no_brief_unblocks_ui_wo(
    patched_paths, db_path: Path, tmp_path: Path
) -> None:
    from core.projects.start import start_project

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE business_work_orders SET work_order_type = 'ui_page' WHERE work_order_id = ?",
        (WO_OPEN_ID,),
    )
    conn.commit()
    conn.close()

    result = start_project(
        project_id=PROJECT_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
        accept_no_brief=True,
    )
    assert result["ok"] is True
    assert result["work_order_start"]["ok"] is True
