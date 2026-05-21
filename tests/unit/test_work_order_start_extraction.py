"""Direct-call tests for the A2 split of `_work_order_start` into three
pure functions in `core.work_orders.start`."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-05-20T00:00:00+00:00"
WO_ID = "wo-test-1234-5678-90ab-cdef-12345678"
UI_WO_ID = "wo-test-ui12-3456-78ab-cdef-12345678"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    target = tmp_path / "studio.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(target)
    # Seed a UI-typed work order and a non-UI work order.
    conn = sqlite3.connect(str(target))
    conn.execute(
        "INSERT INTO ds_projects VALUES (?, ?, ?, ?, ?, ?)",
        ("p1", "Test Project", "", "active", NOW, NOW),
    )
    conn.execute(
        "INSERT INTO ds_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, status,"
        " work_order_type, created_at, updated_at)"
        " VALUES (?, ?, NULL, ?, '', 'open', 'api_endpoint', ?, ?)",
        (WO_ID, "p1", "Backend WO", NOW, NOW),
    )
    conn.execute(
        "INSERT INTO ds_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, status,"
        " work_order_type, created_at, updated_at)"
        " VALUES (?, ?, NULL, ?, '', 'open', 'ui_page', ?, ?)",
        (UI_WO_ID, "p1", "UI WO", NOW, NOW),
    )
    conn.commit()
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


# ── read_work_order_brief ─────────────────────────────────────────────────────


def test_read_work_order_brief_returns_full_dict(patched_paths, tmp_path: Path) -> None:
    from core.work_orders.start import read_work_order_brief

    result = read_work_order_brief(
        work_order_id=WO_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert result["ok"] is True
    assert result["work_order_id"] == WO_ID
    assert result["title"] == "Backend WO"
    assert result["type_id"] == "api_endpoint"
    assert result["project_id"] == "p1"
    assert result["project_name"] == "Test Project"
    assert result["pending_tasks"] == []
    assert result["brief_warning"] is False  # non-UI type
    assert result["brief_locked"] is None
    assert result["blocking_milestone_count"] == 0


def test_read_work_order_brief_flags_warning_for_ui_without_brief(
    patched_paths, tmp_path: Path
) -> None:
    from core.work_orders.start import read_work_order_brief

    result = read_work_order_brief(
        work_order_id=UI_WO_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert result["ok"] is True
    assert result["brief_warning"] is True
    assert result["brief_locked"] is None


def test_read_work_order_brief_unknown_returns_error(patched_paths, tmp_path: Path) -> None:
    from core.work_orders.start import read_work_order_brief

    result = read_work_order_brief(
        work_order_id="nope",
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert result["ok"] is False
    assert "not found" in result["error"]


# ── write_work_order_context ──────────────────────────────────────────────────


def test_write_work_order_context_creates_file_with_enforcement_block(
    patched_paths, tmp_path: Path
) -> None:
    from core.work_orders.start import read_work_order_brief, write_work_order_context

    brief = read_work_order_brief(
        work_order_id=WO_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    planning_root = tmp_path / ".planning"
    context_path = write_work_order_context(brief, planning_root=planning_root, now=NOW)

    assert context_path == planning_root / "work-orders" / WO_ID / "context.md"
    assert context_path.is_file()
    content = context_path.read_text(encoding="utf-8")
    assert "# Work Order: Backend WO" in content
    assert "DREAM STUDIO ENFORCEMENT" in content
    assert NOW in content


def test_write_work_order_context_renders_brief_warning_for_ui_no_brief(
    patched_paths, tmp_path: Path
) -> None:
    from core.work_orders.start import read_work_order_brief, write_work_order_context

    brief = read_work_order_brief(
        work_order_id=UI_WO_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    context_path = write_work_order_context(brief, planning_root=tmp_path / ".planning", now=NOW)
    content = context_path.read_text(encoding="utf-8")
    assert "WARNING" in content
    assert "website:discover" in content


def test_write_work_order_context_enforcement_block_contains_no_cli_commands(
    patched_paths, tmp_path: Path
) -> None:
    import re

    from core.work_orders.start import read_work_order_brief, write_work_order_context

    brief = read_work_order_brief(
        work_order_id=WO_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    context_path = write_work_order_context(brief, planning_root=tmp_path / ".planning", now=NOW)
    content = context_path.read_text(encoding="utf-8")
    assert not re.search(
        r"py -m interfaces\.cli\.ds", content
    ), "context.md enforcement block must not contain CLI commands"
    assert "ds-workorder:execute" in content
    assert "ds-workorder:close" in content


def test_write_work_order_context_rejects_failed_brief(tmp_path: Path) -> None:
    from core.work_orders.start import write_work_order_context

    with pytest.raises(ValueError):
        write_work_order_context(
            {"ok": False, "error": "boom"},
            planning_root=tmp_path / ".planning",
        )


# ── start_work_order ──────────────────────────────────────────────────────────


def test_start_work_order_succeeds_for_non_ui_type(patched_paths, tmp_path: Path) -> None:
    from core.work_orders.start import start_work_order

    result = start_work_order(
        work_order_id=WO_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    assert result["ok"] is True
    assert result["work_order_id"] == WO_ID
    assert "context_path" in result
    assert Path(result["context_path"]).is_file()


def test_start_work_order_blocks_ui_without_brief_unless_accepted(
    patched_paths, tmp_path: Path
) -> None:
    from core.work_orders.start import start_work_order

    blocked = start_work_order(
        work_order_id=UI_WO_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    assert blocked["ok"] is False
    assert blocked.get("requires_brief_confirmation") is True

    accepted = start_work_order(
        work_order_id=UI_WO_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
        accept_no_brief=True,
    )
    assert accepted["ok"] is True


def test_start_work_order_blocks_when_earlier_milestone_incomplete(
    patched_paths, db_path: Path, tmp_path: Path
) -> None:
    from core.work_orders.start import start_work_order

    # Add two milestones with order_index 0 and 1, and an open WO in milestone 0.
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO ds_milestones"
        " (milestone_id, project_id, title, description, status, order_index, created_at, updated_at)"
        " VALUES (?, ?, ?, '', 'pending', ?, ?, ?)",
        ("ms0", "p1", "First", 0, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO ds_milestones"
        " (milestone_id, project_id, title, description, status, order_index, created_at, updated_at)"
        " VALUES (?, ?, ?, '', 'pending', ?, ?, ?)",
        ("ms1", "p1", "Second", 1, NOW, NOW),
    )
    # Add a still-open WO in milestone 0.
    conn.execute(
        "INSERT INTO ds_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, status,"
        " work_order_type, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, '', 'open', 'api_endpoint', ?, ?)",
        ("wo-blocker", "p1", "ms0", "Earlier", NOW, NOW),
    )
    # Move the target WO into milestone 1.
    conn.execute(
        "UPDATE ds_work_orders SET milestone_id = 'ms1' WHERE work_order_id = ?",
        (WO_ID,),
    )
    conn.commit()
    conn.close()

    result = start_work_order(
        work_order_id=WO_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    assert result["ok"] is False
    assert "earlier milestones are incomplete" in result["error"]


def test_start_work_order_unknown_returns_error(patched_paths, tmp_path: Path) -> None:
    from core.work_orders.start import start_work_order

    result = start_work_order(
        work_order_id="nope",
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    assert result["ok"] is False
    assert "not found" in result["error"]
