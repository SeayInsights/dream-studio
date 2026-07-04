"""Workstream 3 gate: `ds project register` CLI command assertions."""

from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]

NOW = "2026-05-16T00:00:00+00:00"


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "studio.db"
    bootstrap_database(db_path)
    return db_path


def _make_full_db(tmp_path: Path) -> Path:
    """Bootstrap a complete Dream Studio schema (all migrations)."""
    db_path = tmp_path / "studio.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(db_path)
    return db_path


def _seed_project(
    db_path: Path, *, project_id: str, name: str = "P", status: str = "active"
) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO business_projects (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?)",
        (project_id, name, "", status, NOW, NOW),
    )
    conn.commit()
    conn.close()


def _run_cli(argv: list[str]) -> tuple[int, str]:
    import io
    import sys
    from interfaces.cli.ds import main

    captured = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured
    try:
        code = main(argv)
    finally:
        sys.stdout = old_stdout
    return code, captured.getvalue()


def test_project_register_inserts_row(tmp_path):
    db_path = _make_db(tmp_path)

    from interfaces.cli.commands.project import _project_register

    fake_paths = MagicMock()
    fake_paths.sqlite_path = db_path

    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        code = _project_register(
            name="My Project",
            description="A test project",
            project_path=REPO_ROOT,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
        )

    assert code == 0

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("SELECT name, status FROM business_projects").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0][0] == "My Project"
    assert rows[0][1] == "active"


def test_project_register_output_has_project_id(tmp_path, capsys):
    db_path = _make_db(tmp_path)

    from interfaces.cli.commands.project import _project_register
    from unittest.mock import MagicMock, patch

    fake_paths = MagicMock()
    fake_paths.sqlite_path = db_path

    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        code = _project_register(
            name="Proj2",
            description="",
            project_path=REPO_ROOT,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
        )

    captured = capsys.readouterr()
    assert code == 0
    result = json.loads(captured.out)
    assert result["ok"] is True
    assert "project_id" in result
    assert len(result["project_id"]) == 36  # UUID4 format
    assert result["name"] == "Proj2"
    assert result["status"] == "active"


def test_project_register_missing_db_raises(tmp_path):
    from interfaces.cli.commands.project import _project_register

    fake_paths = MagicMock()
    fake_paths.sqlite_path = tmp_path / "nonexistent.db"

    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        with pytest.raises(RuntimeError, match="SQLite authority is missing"):
            _project_register(
                name="Fail Project",
                description="",
                project_path=REPO_ROOT,
                source_root=REPO_ROOT,
                dream_studio_home=tmp_path,
            )


def test_project_subparser_registered():
    import argparse
    from interfaces.cli.ds import main

    # Verify the subparser exists by checking --help output doesn't crash
    try:
        main(["project", "--help"])
    except SystemExit as e:
        assert e.code == 0


def test_project_register_output_contains_set_active_hint(tmp_path, capsys):
    db_path = _make_db(tmp_path)
    fake_paths = MagicMock()
    fake_paths.sqlite_path = db_path

    from interfaces.cli.commands.project import _project_register

    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        _project_register(
            name="Hinted",
            description="",
            project_path=REPO_ROOT,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
        )

    result = json.loads(capsys.readouterr().out)
    assert "hint" in result
    assert "set-active" in result["hint"]


# ── WS 8b-2: set-active / deactivate ─────────────────────────────────────────


def test_set_active_makes_target_active(tmp_path, capsys):
    db_path = _make_db(tmp_path)
    pid = "11111111-1111-1111-1111-111111111111"
    _seed_project(db_path, project_id=pid, name="Target", status="paused")

    from interfaces.cli.commands.project import _project_set_active

    fake_paths = MagicMock()
    fake_paths.sqlite_path = db_path

    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        rc = _project_set_active(
            project_id=pid,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
        )

    assert rc == 0
    row = (
        sqlite3.connect(str(db_path))
        .execute("SELECT status FROM business_projects WHERE project_id = ?", (pid,))
        .fetchone()
    )
    assert row[0] == "active"


def test_set_active_deactivates_previously_active(tmp_path, capsys):
    db_path = _make_db(tmp_path)
    pid_old = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    pid_new = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    _seed_project(db_path, project_id=pid_old, name="Old", status="active")
    _seed_project(db_path, project_id=pid_new, name="New", status="paused")

    from interfaces.cli.commands.project import _project_set_active

    fake_paths = MagicMock()
    fake_paths.sqlite_path = db_path

    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        rc = _project_set_active(
            project_id=pid_new,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
        )

    assert rc == 0
    conn = sqlite3.connect(str(db_path))
    old_status = conn.execute(
        "SELECT status FROM business_projects WHERE project_id = ?", (pid_old,)
    ).fetchone()[0]
    new_status = conn.execute(
        "SELECT status FROM business_projects WHERE project_id = ?", (pid_new,)
    ).fetchone()[0]
    conn.close()
    assert old_status == "paused"
    assert new_status == "active"


def test_set_active_returns_1_for_unknown_project(tmp_path, capsys):
    db_path = _make_db(tmp_path)
    fake_paths = MagicMock()
    fake_paths.sqlite_path = db_path

    from interfaces.cli.commands.project import _project_set_active

    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        rc = _project_set_active(
            project_id="00000000-0000-0000-0000-000000000000",
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
        )

    assert rc == 1
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is False


def test_deactivate_changes_status_to_inactive(tmp_path, capsys):
    db_path = _make_db(tmp_path)
    pid = "cccccccc-cccc-cccc-cccc-cccccccccccc"
    _seed_project(db_path, project_id=pid, name="Deactivate Me", status="active")

    from interfaces.cli.commands.project import _project_deactivate

    fake_paths = MagicMock()
    fake_paths.sqlite_path = db_path

    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        rc = _project_deactivate(
            project_id=pid,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
        )

    assert rc == 0
    row = (
        sqlite3.connect(str(db_path))
        .execute("SELECT status FROM business_projects WHERE project_id = ?", (pid,))
        .fetchone()
    )
    assert row[0] == "paused"


# ── WS 8b-3: delete ──────────────────────────────────────────────────────────


def test_delete_removes_project_with_no_dependents(tmp_path, capsys):
    db_path = _make_full_db(tmp_path)
    pid = "dddddddd-dddd-dddd-dddd-dddddddddddd"
    _seed_project(db_path, project_id=pid, name="Empty Project")

    from interfaces.cli.commands.project import _project_delete

    fake_paths = MagicMock()
    fake_paths.sqlite_path = db_path

    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        rc = _project_delete(
            project_id=pid,
            confirm=False,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
        )

    assert rc == 0
    row = (
        sqlite3.connect(str(db_path))
        .execute("SELECT project_id FROM business_projects WHERE project_id = ?", (pid,))
        .fetchone()
    )
    assert row is None


def test_delete_requires_confirm_when_dependents_exist(tmp_path, capsys):
    db_path = _make_full_db(tmp_path)
    pid = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
    _seed_project(db_path, project_id=pid, name="Has Dependents")
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, title, status, created_at, updated_at)"
        " VALUES ('wo-test', ?, 'WO', 'created', ?, ?)",
        (pid, NOW, NOW),
    )
    conn.commit()
    conn.close()

    from interfaces.cli.commands.project import _project_delete

    fake_paths = MagicMock()
    fake_paths.sqlite_path = db_path

    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        rc = _project_delete(
            project_id=pid,
            confirm=False,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
        )

    assert rc == 1
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is False
    assert "confirm" in result["error"].lower()


def test_delete_cascade_removes_all_dependents(tmp_path, capsys):
    db_path = _make_full_db(tmp_path)
    pid = "ffffffff-ffff-ffff-ffff-ffffffffffff"
    _seed_project(db_path, project_id=pid, name="Big Project")
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, title, status, created_at, updated_at)"
        " VALUES ('wo-cascade', ?, 'WO', 'created', ?, ?)",
        (pid, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_tasks"
        " (task_id, work_order_id, project_id, title, status, created_at, updated_at)"
        " VALUES ('task-cascade', 'wo-cascade', ?, 'T', 'pending', ?, ?)",
        (pid, NOW, NOW),
    )
    conn.commit()
    conn.close()

    from interfaces.cli.commands.project import _project_delete

    fake_paths = MagicMock()
    fake_paths.sqlite_path = db_path

    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        rc = _project_delete(
            project_id=pid,
            confirm=True,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
        )

    assert rc == 0
    conn2 = sqlite3.connect(str(db_path))
    assert (
        conn2.execute(
            "SELECT COUNT(*) FROM business_projects WHERE project_id = ?", (pid,)
        ).fetchone()[0]
        == 0
    )
    assert (
        conn2.execute(
            "SELECT COUNT(*) FROM business_work_orders WHERE project_id = ?", (pid,)
        ).fetchone()[0]
        == 0
    )
    assert (
        conn2.execute(
            "SELECT COUNT(*) FROM business_tasks WHERE project_id = ?", (pid,)
        ).fetchone()[0]
        == 0
    )
    conn2.close()


def test_delete_returns_1_for_unknown_project(tmp_path, capsys):
    db_path = _make_full_db(tmp_path)
    fake_paths = MagicMock()
    fake_paths.sqlite_path = db_path

    from interfaces.cli.commands.project import _project_delete

    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        rc = _project_delete(
            project_id="00000000-0000-0000-0000-000000000000",
            confirm=True,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
        )

    assert rc == 1
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is False
