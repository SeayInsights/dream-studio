"""Workstream 5b gate: project spine wiring — marker file, emitter, CLI list/status/next."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_048 = REPO_ROOT / "core" / "event_store" / "migrations" / "048_project_spine.sql"
MIGRATION_049 = REPO_ROOT / "core" / "event_store" / "migrations" / "049_work_order_type.sql"


# ── DB helpers ────────────────────────────────────────────────────────────────


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "studio.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(MIGRATION_048.read_text(encoding="utf-8"))
    conn.executescript(MIGRATION_049.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    return db_path


def _seed_project(db_path: Path, *, project_id: str, name: str = "P") -> None:
    now = "2026-05-16T00:00:00+00:00"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO ds_projects VALUES (?,?,?,'active',?,?)", (project_id, name, "", now, now)
    )
    conn.commit()
    conn.close()


def _seed_work_order(
    db_path: Path,
    *,
    work_order_id: str,
    project_id: str,
    title: str = "WO",
    status: str = "open",
    work_order_type: str | None = None,
) -> None:
    now = "2026-05-16T00:00:00+00:00"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO ds_work_orders"
        " (work_order_id, project_id, title, status, work_order_type, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (work_order_id, project_id, title, status, work_order_type, now, now),
    )
    conn.commit()
    conn.close()


# ── read_project_id tests ─────────────────────────────────────────────────────


def test_read_project_id_returns_uuid_when_marker_present(tmp_path):
    from emitters.claude_code.project import read_project_id

    pid = "12345678-1234-1234-1234-123456789abc"
    (tmp_path / ".dream-studio-project").write_text(pid + "\n", encoding="utf-8")
    assert read_project_id(tmp_path) == pid


def test_read_project_id_returns_none_when_absent(tmp_path):
    from emitters.claude_code.project import read_project_id

    assert read_project_id(tmp_path) is None


def test_read_project_id_returns_none_and_warns_when_malformed(tmp_path, caplog):
    import logging
    from emitters.claude_code.project import read_project_id

    (tmp_path / ".dream-studio-project").write_text("not-a-uuid\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="emitters.claude_code.project"):
        result = read_project_id(tmp_path)
    assert result is None
    assert "Malformed" in caplog.text or "not a UUID" in caplog.text.lower() or caplog.records


# ── get_active_project_id ─────────────────────────────────────────────────────


def test_get_active_project_id_returns_id_when_active_project_exists(tmp_path):
    from emitters.claude_code.project import get_active_project_id

    db_path = _make_db(tmp_path)
    pid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    _seed_project(db_path, project_id=pid, name="Active")
    assert get_active_project_id(db_path) == pid


def test_get_active_project_id_returns_none_when_no_active_project(tmp_path):
    from emitters.claude_code.project import get_active_project_id

    db_path = _make_db(tmp_path)
    # No project seeded — table is empty.
    assert get_active_project_id(db_path) is None


def test_get_active_project_id_returns_none_when_db_missing(tmp_path):
    from emitters.claude_code.project import get_active_project_id

    assert get_active_project_id(tmp_path / "no-such.db") is None


def test_get_active_project_id_returns_most_recent_when_multiple_active(tmp_path):
    from emitters.claude_code.project import get_active_project_id
    import sqlite3 as _sqlite3

    db_path = _make_db(tmp_path)
    pid_old = "11111111-1111-1111-1111-111111111111"
    pid_new = "22222222-2222-2222-2222-222222222222"
    conn = _sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO ds_projects VALUES (?,?,?,'active','2026-05-01T00:00:00+00:00','2026-05-01T00:00:00+00:00')",
        (pid_old, "Old", ""),
    )
    conn.execute(
        "INSERT INTO ds_projects VALUES (?,?,?,'active','2026-05-10T00:00:00+00:00','2026-05-10T00:00:00+00:00')",
        (pid_new, "New", ""),
    )
    conn.commit()
    conn.close()
    assert get_active_project_id(db_path) == pid_new


# ── emitter project_id wiring ─────────────────────────────────────────────────


def test_emitter_populates_project_id_from_active_project(tmp_path, spool_root):
    import emitters.claude_code.emitter as emitter_module
    from emitters.claude_code.emitter import normalize_user_prompt_submit

    pid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    db_path = _make_db(tmp_path)
    _seed_project(db_path, project_id=pid, name="Active Project")

    # Patch the name as imported into emitter.py's namespace.
    with patch.object(emitter_module, "_get_db_path", return_value=db_path):
        envelopes = normalize_user_prompt_submit({"prompt": "hello"}, root=tmp_path)
    assert len(envelopes) == 1
    assert envelopes[0].project_id == pid


def test_emitter_project_id_null_when_no_active_project(tmp_path, spool_root):
    import emitters.claude_code.emitter as emitter_module
    from emitters.claude_code.emitter import normalize_user_prompt_submit

    db_path = _make_db(tmp_path)
    # No active project seeded — empty table.

    with patch.object(emitter_module, "_get_db_path", return_value=db_path):
        envelopes = normalize_user_prompt_submit({"prompt": "hello"}, root=tmp_path)
    assert len(envelopes) == 1
    assert envelopes[0].project_id is None


# ── ds project list ───────────────────────────────────────────────────────────


def test_project_list_shows_registered_projects(tmp_path, capsys):
    db_path = _make_db(tmp_path)
    pid = "11111111-1111-1111-1111-111111111111"
    _seed_project(db_path, project_id=pid, name="Listed Project")

    from interfaces.cli.ds import _project_list
    from unittest.mock import MagicMock

    fake_paths = MagicMock()
    fake_paths.sqlite_path = db_path

    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        code = _project_list(
            status_filter="active",
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
        )

    captured = capsys.readouterr()
    assert code == 0
    result = json.loads(captured.out)
    assert result["ok"] is True
    names = [p["name"] for p in result["projects"]]
    assert "Listed Project" in names


# ── ds project status ─────────────────────────────────────────────────────────


def test_project_status_shows_milestone_and_work_order_counts(tmp_path, capsys):
    db_path = _make_db(tmp_path)
    pid = "22222222-2222-2222-2222-222222222222"
    _seed_project(db_path, project_id=pid, name="Status Project")
    _seed_work_order(db_path, work_order_id="wo-1", project_id=pid, title="WO1", status="open")
    _seed_work_order(db_path, work_order_id="wo-2", project_id=pid, title="WO2", status="complete")

    from interfaces.cli.ds import _project_status
    from unittest.mock import MagicMock

    fake_paths = MagicMock()
    fake_paths.sqlite_path = db_path

    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        code = _project_status(
            project_id=pid,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
        )

    captured = capsys.readouterr()
    assert code == 0
    result = json.loads(captured.out)
    assert result["ok"] is True
    assert result["work_order_count"] == 2
    assert result["open_work_order_count"] == 1


# ── ds project next ───────────────────────────────────────────────────────────


def test_project_next_returns_first_open_work_order(tmp_path, capsys):
    db_path = _make_db(tmp_path)
    pid = "33333333-3333-3333-3333-333333333333"
    _seed_project(db_path, project_id=pid, name="Next Project")
    _seed_work_order(db_path, work_order_id="wo-next", project_id=pid, title="First WO", status="open")

    from interfaces.cli.ds import _project_next
    from unittest.mock import MagicMock

    fake_paths = MagicMock()
    fake_paths.sqlite_path = db_path

    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        code = _project_next(
            project_id=pid,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
        )

    captured = capsys.readouterr()
    assert code == 0
    result = json.loads(captured.out)
    assert result["ok"] is True
    assert result["work_order"]["work_order_id"] == "wo-next"


def test_project_next_returns_none_when_no_open_work_orders(tmp_path, capsys):
    db_path = _make_db(tmp_path)
    pid = "44444444-4444-4444-4444-444444444444"
    _seed_project(db_path, project_id=pid, name="Empty Project")

    from interfaces.cli.ds import _project_next
    from unittest.mock import MagicMock

    fake_paths = MagicMock()
    fake_paths.sqlite_path = db_path

    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        code = _project_next(
            project_id=pid,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
        )

    captured = capsys.readouterr()
    assert code == 0
    result = json.loads(captured.out)
    assert result["ok"] is True
    assert result["work_order"] is None
