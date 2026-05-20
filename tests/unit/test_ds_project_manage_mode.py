"""A6.3 — ds-project:manage mode + delete_project lift.

Tests the new ``manage`` mode under the existing ``ds-project`` pack
and the ``core.projects.mutations.delete_project`` function lifted out
of ``_project_delete``.
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


def test_manage_mode_registered_in_packs_yaml() -> None:
    import yaml

    data = yaml.safe_load((REPO_ROOT / "packs.yaml").read_text(encoding="utf-8"))
    cfg = data["packs"][PACK_NAME]
    assert MODE_NAME in cfg["modes"], f"{MODE_NAME!r} missing from ds-project modes"


def test_manage_mode_files_exist() -> None:
    mode_dir = REPO_ROOT / "canonical" / "skills" / PACK_NAME / "modes" / MODE_NAME
    assert (mode_dir / "SKILL.md").is_file()
    assert (mode_dir / "metadata.yml").is_file()


def test_manage_mode_metadata_has_spec_triggers_and_token_estimate() -> None:
    import yaml

    metadata = REPO_ROOT / "canonical" / "skills" / PACK_NAME / "modes" / MODE_NAME / "metadata.yml"
    data = yaml.safe_load(metadata.read_text(encoding="utf-8"))
    triggers = set(data.get("triggers", []))
    expected = {"list projects:", "switch project:", "archive project:", "delete project:"}
    assert expected <= triggers, f"missing spec triggers: {expected - triggers}"
    assert isinstance(data.get("estimated_tokens"), int) and data["estimated_tokens"] > 0


def test_load_skill_content_resolves_manage_mode() -> None:
    from core.skills.invocation import load_skill_content

    result = load_skill_content(specifier=f"{PACK_NAME}:{MODE_NAME}", source_root=REPO_ROOT)
    assert result["ok"] is True, f"load failed: {result.get('error')}"
    assert result["pack"] == PACK_NAME
    assert result["mode"] == MODE_NAME


def test_manage_mode_names_each_project_function() -> None:
    """AI-presents-from-database discipline: the manage mode SKILL.md
    must name every project lifecycle function it wraps."""

    skill_md = REPO_ROOT / "canonical" / "skills" / PACK_NAME / "modes" / MODE_NAME / "SKILL.md"
    content = skill_md.read_text(encoding="utf-8")
    for fn in (
        "get_project_list",
        "set_active_project",
        "deactivate_project",
        "delete_project",
    ):
        assert fn in content, f"manage mode does not reference {fn}"


def test_manage_mode_skill_md_has_no_legacy_cli_commands() -> None:
    skill_md = REPO_ROOT / "canonical" / "skills" / PACK_NAME / "modes" / MODE_NAME / "SKILL.md"
    content = skill_md.read_text(encoding="utf-8")
    assert "py -m interfaces.cli.ds" not in content


def test_pack_skill_md_dispatch_table_lists_manage() -> None:
    pack_skill = REPO_ROOT / "canonical" / "skills" / PACK_NAME / "SKILL.md"
    content = pack_skill.read_text(encoding="utf-8")
    assert "| manage |" in content, "ds-project SKILL.md dispatch table missing manage row"


# ── delete_project direct-call tests ──────────────────────────────────────────


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    target = tmp_path / "studio.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(target)
    conn = sqlite3.connect(str(target))
    try:
        conn.execute(
            "INSERT INTO ds_projects VALUES (?, ?, ?, ?, ?, ?)",
            (PROJECT_ID, "Manage Ext Project", "", "active", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO ds_milestones"
            " (milestone_id, project_id, title, description, status, order_index,"
            " created_at, updated_at)"
            " VALUES (?, ?, ?, '', 'pending', 0, ?, ?)",
            ("ms-manage-1", PROJECT_ID, "First", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO ds_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, '', 'open', 'api_endpoint', ?, ?)",
            ("wo-manage-1", PROJECT_ID, "ms-manage-1", "WO", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO ds_tasks"
            " (task_id, project_id, work_order_id, title, description, status,"
            " created_at, updated_at)"
            " VALUES (?, ?, ?, ?, '', 'pending', ?, ?)",
            ("task-manage-1", PROJECT_ID, "wo-manage-1", "Task", NOW, NOW),
        )
        # A second project with no dependents — used to test the no-confirm
        # cascade path (deletes cleanly because there's nothing to cascade).
        conn.execute(
            "INSERT INTO ds_projects VALUES (?, ?, ?, ?, ?, ?)",
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
            "SELECT project_id FROM ds_projects WHERE project_id = ?", (PROJECT_ID,)
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

    with sqlite3.connect(str(db_path)) as conn:
        proj = conn.execute(
            "SELECT 1 FROM ds_projects WHERE project_id = ?", (PROJECT_ID,)
        ).fetchone()
        ms = conn.execute(
            "SELECT 1 FROM ds_milestones WHERE project_id = ?", (PROJECT_ID,)
        ).fetchone()
        wo = conn.execute(
            "SELECT 1 FROM ds_work_orders WHERE project_id = ?", (PROJECT_ID,)
        ).fetchone()
        tasks = conn.execute(
            "SELECT 1 FROM ds_tasks WHERE project_id = ?", (PROJECT_ID,)
        ).fetchone()
    assert proj is None
    assert ms is None
    assert wo is None
    assert tasks is None


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
