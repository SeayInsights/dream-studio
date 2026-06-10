"""Direct-call tests for the 22 handler functions extracted in A1.

These tests assert on the returned dict directly, without going through the
CLI subprocess or stdout-JSON parsing. They prove the new pure-function entry
points are import-callable from skills, workflows, and hooks.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-05-20T00:00:00+00:00"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Fully-bootstrapped Dream Studio SQLite, returned as a path."""

    target = tmp_path / "studio.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(target)
    return target


@pytest.fixture
def patched_paths(db_path: Path, tmp_path: Path):
    """Patch `interfaces.cli.ds.resolve_installed_runtime_paths` so the
    lazy-imported `_require_db` in core modules sees `db_path`."""

    fake = MagicMock()
    fake.sqlite_path = db_path
    fake.source_root = REPO_ROOT
    fake.dream_studio_home = tmp_path
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake):
        yield fake


def _seed_project(
    db_path: Path, *, project_id: str, name: str = "P", status: str = "active"
) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO business_projects (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (project_id, name, "", status, NOW, NOW),
    )
    conn.commit()
    conn.close()


def _seed_work_order(
    db_path: Path,
    *,
    work_order_id: str,
    project_id: str,
    title: str = "Build it",
    work_order_type: str = "ui_page",
    status: str = "created",
) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, status,"
        " work_order_type, created_at, updated_at)"
        " VALUES (?, ?, NULL, ?, '', ?, ?, ?, ?)",
        (work_order_id, project_id, title, status, work_order_type, NOW, NOW),
    )
    conn.commit()
    conn.close()


def _seed_brief(db_path: Path, *, brief_id: str, project_id: str, status: str = "draft") -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO business_design_briefs"
        " (brief_id, project_id, status, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (brief_id, project_id, status, NOW, NOW),
    )
    conn.commit()
    conn.close()


# ── core.projects.queries ─────────────────────────────────────────────────────


def test_get_project_list_returns_dict(patched_paths, db_path: Path, tmp_path: Path) -> None:
    from core.projects.queries import get_project_list

    _seed_project(db_path, project_id="p1", name="First")

    result = get_project_list(source_root=REPO_ROOT, dream_studio_home=tmp_path)

    assert result["ok"] is True
    assert len(result["projects"]) == 1
    assert result["projects"][0]["project_id"] == "p1"


def test_get_project_status_unknown_project_returns_error_dict(
    patched_paths, db_path: Path, tmp_path: Path
) -> None:
    from core.projects.queries import get_project_status

    result = get_project_status(
        project_id="nope", source_root=REPO_ROOT, dream_studio_home=tmp_path
    )
    assert result["ok"] is False
    assert "Project not found" in result["error"]


def test_get_next_work_order_returns_none_when_no_work_orders(
    patched_paths, db_path: Path, tmp_path: Path
) -> None:
    from core.projects.queries import get_next_work_order

    _seed_project(db_path, project_id="p1")
    result = get_next_work_order(project_id="p1", source_root=REPO_ROOT, dream_studio_home=tmp_path)
    assert result["ok"] is True
    assert result["work_order"] is None


def test_get_project_state_returns_empty_projects_when_none_active(
    patched_paths, db_path: Path, tmp_path: Path
) -> None:
    from core.projects.queries import get_project_state

    result = get_project_state(source_root=REPO_ROOT, dream_studio_home=tmp_path)
    assert result["ok"] is True
    assert result["projects"] == []
    assert "No active projects" in result["next_action"]


# ── core.projects.mutations ───────────────────────────────────────────────────


def test_set_active_project_returns_ok_dict(patched_paths, db_path: Path, tmp_path: Path) -> None:
    from core.projects.mutations import set_active_project

    _seed_project(db_path, project_id="p1", status="paused")
    result = set_active_project(project_id="p1", source_root=REPO_ROOT, dream_studio_home=tmp_path)
    assert result == {"ok": True, "project_id": "p1", "status": "active"}


def test_set_active_project_unknown_returns_error(
    patched_paths, db_path: Path, tmp_path: Path
) -> None:
    from core.projects.mutations import set_active_project

    result = set_active_project(
        project_id="nope", source_root=REPO_ROOT, dream_studio_home=tmp_path
    )
    assert result["ok"] is False


def test_deactivate_project_returns_ok_dict(patched_paths, db_path: Path, tmp_path: Path) -> None:
    from core.projects.mutations import deactivate_project

    _seed_project(db_path, project_id="p1")
    result = deactivate_project(project_id="p1", source_root=REPO_ROOT, dream_studio_home=tmp_path)
    assert result == {"ok": True, "project_id": "p1", "status": "paused"}


# ── core.work_orders.queries ──────────────────────────────────────────────────


def test_list_work_orders_returns_filtered(patched_paths, db_path: Path, tmp_path: Path) -> None:
    from core.work_orders.queries import list_work_orders

    _seed_project(db_path, project_id="p1")
    _seed_work_order(db_path, work_order_id="w1", project_id="p1", status="open")
    _seed_work_order(db_path, work_order_id="w2", project_id="p1", status="complete")

    result = list_work_orders(
        project_id="p1",
        status_filter="open",
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert result["ok"] is True
    assert len(result["work_orders"]) == 1
    assert result["work_orders"][0]["id"] == "w1"


def test_list_tasks_unknown_work_order_returns_error(
    patched_paths, db_path: Path, tmp_path: Path
) -> None:
    from core.work_orders.queries import list_tasks

    result = list_tasks(work_order_id="nope", source_root=REPO_ROOT, dream_studio_home=tmp_path)
    assert result["ok"] is False


# ── core.work_orders.mutations ────────────────────────────────────────────────


def test_block_work_order_returns_ok_dict(patched_paths, db_path: Path, tmp_path: Path) -> None:
    from core.work_orders.mutations import block_work_order

    _seed_project(db_path, project_id="p1")
    _seed_work_order(db_path, work_order_id="w1", project_id="p1")

    result = block_work_order(
        work_order_id="w1",
        reason="awaiting upstream",
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert result["ok"] is True
    assert result["status"] == "blocked"
    assert result["block_reason"] == "awaiting upstream"


def test_unblock_work_order_rejects_non_blocked(
    patched_paths, db_path: Path, tmp_path: Path
) -> None:
    from core.work_orders.mutations import unblock_work_order

    _seed_project(db_path, project_id="p1")
    _seed_work_order(db_path, work_order_id="w1", project_id="p1", status="open")

    result = unblock_work_order(
        work_order_id="w1", source_root=REPO_ROOT, dream_studio_home=tmp_path
    )
    assert result["ok"] is False
    assert "not blocked" in result["error"]


# ── core.design_briefs ────────────────────────────────────────────────────────


def test_get_design_brief_returns_brief_when_present(
    patched_paths, db_path: Path, tmp_path: Path
) -> None:
    from core.design_briefs.queries import get_design_brief

    _seed_project(db_path, project_id="p1")
    _seed_brief(db_path, brief_id="b1", project_id="p1", status="draft")

    result = get_design_brief(project_id="p1", source_root=REPO_ROOT, dream_studio_home=tmp_path)
    assert result["ok"] is True
    assert result["brief_id"] == "b1"


def test_get_design_brief_returns_sentinel_when_absent(
    patched_paths, db_path: Path, tmp_path: Path
) -> None:
    from core.design_briefs.queries import get_design_brief

    result = get_design_brief(
        project_id="missing", source_root=REPO_ROOT, dream_studio_home=tmp_path
    )
    assert result["ok"] is True
    assert result["brief"] is None
    assert "message" in result


def test_update_design_brief_field_rejects_unknown_field(
    patched_paths, db_path: Path, tmp_path: Path
) -> None:
    from core.design_briefs.mutations import update_design_brief_field

    _seed_project(db_path, project_id="p1")
    _seed_brief(db_path, brief_id="b1", project_id="p1")

    result = update_design_brief_field(
        brief_id="b1",
        field="not_a_field",
        value="anything",
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert result["ok"] is False
    assert "Unknown field" in result["error"]


def test_set_design_system_rejects_invalid_system(
    patched_paths, db_path: Path, tmp_path: Path
) -> None:
    from core.design_briefs.mutations import set_design_system

    _seed_project(db_path, project_id="p1")
    _seed_brief(db_path, brief_id="b1", project_id="p1")

    result = set_design_system(
        brief_id="b1",
        system_name="bad-system",
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert result["ok"] is False
    assert "Invalid design system" in result["error"]


# ── core.milestones.queries ───────────────────────────────────────────────────


def test_list_milestones_returns_empty_for_new_project(
    patched_paths, db_path: Path, tmp_path: Path
) -> None:
    from core.milestones.queries import list_milestones

    _seed_project(db_path, project_id="p1")
    result = list_milestones(project_id="p1", source_root=REPO_ROOT, dream_studio_home=tmp_path)
    assert result == {"ok": True, "milestones": []}


def test_get_milestone_status_unknown_returns_error(
    patched_paths, db_path: Path, tmp_path: Path
) -> None:
    from core.milestones.queries import get_milestone_status

    result = get_milestone_status(
        milestone_id="nope",
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert result["ok"] is False


# ── core.skills.queries ───────────────────────────────────────────────────────


def test_list_skills_returns_known_packs(tmp_path: Path) -> None:
    from core.skills.queries import list_skills

    result = list_skills(source_root=REPO_ROOT, dream_studio_home=tmp_path)
    assert result["ok"] is True
    assert isinstance(result["skills"], list)
    # Sanity: at least one known pack should appear.
    specifiers = {s["specifier"] for s in result["skills"]}
    assert any(s.startswith("ds-core:") for s in specifiers) or any(
        s.startswith("core:") for s in specifiers
    )


# ── core.health.* ─────────────────────────────────────────────────────────────


def test_get_version_returns_dict(patched_paths, tmp_path: Path) -> None:
    from core.health.version import get_version

    result = get_version(source_root=REPO_ROOT, dream_studio_home=tmp_path)
    assert result["model_name"] == "dream_studio_version_status"
    assert "source_root" in result
    assert "latest_migration_version" in result


def test_run_validation_reports_ready_with_bootstrapped_db(
    patched_paths, db_path: Path, tmp_path: Path
) -> None:
    from core.health.validate import run_validation

    result = run_validation(source_root=REPO_ROOT, dream_studio_home=tmp_path)
    assert result["sqlite_exists"] is True
    assert result["ready"] is True
    assert result["schema_version"] is not None


def test_get_runtime_status_returns_installed_model(patched_paths, tmp_path: Path) -> None:
    from core.health.status import get_runtime_status

    # We patch the actual installed_runtime_model lookup so the test doesn't
    # need a real install on disk.
    with patch("interfaces.cli.ds.installed_runtime_model", return_value={"ok": True}):
        result = get_runtime_status(source_root=REPO_ROOT, dream_studio_home=tmp_path)
    assert result == {"ok": True}


def test_run_doctor_checks_returns_status_field(
    patched_paths, db_path: Path, tmp_path: Path
) -> None:
    from core.health.doctor import run_doctor_checks

    result = run_doctor_checks(source_root=REPO_ROOT, dream_studio_home=tmp_path)
    assert result["model_name"] == "dream_studio_doctor_status"
    assert result["status"] in {"pass", "fail", "warn", "attention_required"}
