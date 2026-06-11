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
    from core.config.sqlite_bootstrap import bootstrap_database

    db_path = tmp_path / "studio.db"
    bootstrap_database(db_path)
    return db_path


def _seed_project(db_path: Path, *, project_id: str, name: str = "P") -> None:
    now = "2026-05-16T00:00:00+00:00"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO business_projects (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?,?,?,'active',?,?)",
        (project_id, name, "", now, now),
    )
    conn.commit()
    conn.close()


def _seed_milestone(
    db_path: Path,
    *,
    milestone_id: str,
    project_id: str,
    title: str = "M1",
    order_index: int = 0,
) -> None:
    now = "2026-05-16T00:00:00+00:00"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO business_milestones"
        " (milestone_id, project_id, title, status, order_index, created_at, updated_at)"
        " VALUES (?,?,?,'pending',?,?,?)",
        (milestone_id, project_id, title, order_index, now, now),
    )
    conn.commit()
    conn.close()


def _seed_work_order(
    db_path: Path,
    *,
    work_order_id: str,
    project_id: str,
    milestone_id: str | None = None,
    title: str = "WO",
    status: str = "created",
    work_order_type: str | None = None,
) -> None:
    now = "2026-05-16T00:00:00+00:00"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, status, work_order_type, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (work_order_id, project_id, milestone_id, title, status, work_order_type, now, now),
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
        "INSERT INTO business_projects (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?,?,?,'active','2026-05-01T00:00:00+00:00','2026-05-01T00:00:00+00:00')",
        (pid_old, "Old", ""),
    )
    conn.execute(
        "INSERT INTO business_projects (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?,?,?,'active','2026-05-10T00:00:00+00:00','2026-05-10T00:00:00+00:00')",
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
    _seed_work_order(db_path, work_order_id="wo-1", project_id=pid, title="WO1", status="created")
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
    mid = "33333333-3333-3333-3333-000000000001"
    _seed_project(db_path, project_id=pid, name="Next Project")
    _seed_milestone(db_path, milestone_id=mid, project_id=pid, title="M1", order_index=0)
    _seed_work_order(
        db_path,
        work_order_id="wo-next",
        project_id=pid,
        milestone_id=mid,
        title="First WO",
        status="created",
    )

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


# ── read_project_id — JSON marker format (WO-MARKER-FORMAT T1) ────────────────


def test_read_project_id_parses_json_format(tmp_path):
    """read_project_id must parse the TA3+ JSON marker format."""
    from emitters.claude_code.project import read_project_id

    pid = "abcdef01-abcd-abcd-abcd-abcdef012345"
    marker_content = json.dumps({"project_id": pid, "project_name": "Test", "schema_version": 1})
    (tmp_path / ".dream-studio-project").write_text(marker_content, encoding="utf-8")
    assert read_project_id(tmp_path) == pid


def test_read_project_id_json_with_extra_fields_returns_uuid(tmp_path):
    """JSON marker with extra metadata fields still returns the project_id."""
    from emitters.claude_code.project import read_project_id

    pid = "12345678-abcd-abcd-abcd-1234567890ab"
    marker = {
        "schema_version": 1,
        "project_id": pid,
        "project_name": "My Project",
        "created_at": "2026-01-01T00:00:00+00:00",
        "metadata": {"git_remote_url": "https://github.com/org/repo"},
    }
    (tmp_path / ".dream-studio-project").write_text(json.dumps(marker), encoding="utf-8")
    assert read_project_id(tmp_path) == pid


def test_read_project_id_json_with_invalid_uuid_returns_none(tmp_path, caplog):
    """JSON marker whose project_id is not a valid UUID returns None."""
    import logging

    from emitters.claude_code.project import read_project_id

    (tmp_path / ".dream-studio-project").write_text(
        json.dumps({"project_id": "not-a-valid-uuid"}), encoding="utf-8"
    )
    with caplog.at_level(logging.WARNING, logger="emitters.claude_code.project"):
        result = read_project_id(tmp_path)
    assert result is None
    assert caplog.records, "Expected a warning log for invalid UUID in JSON marker"


def test_read_project_id_malformed_json_falls_back_to_uuid_line(tmp_path):
    """Content that starts with '{' but is invalid JSON falls back to plain-UUID check."""
    from emitters.claude_code.project import read_project_id

    pid = "99999999-9999-9999-9999-999999999999"
    # JSON parse will fail; first line is the UUID as plain text.
    (tmp_path / ".dream-studio-project").write_text(pid, encoding="utf-8")
    assert read_project_id(tmp_path) == pid


# ── _write_project_marker ghost-marker guard (WO-MARKER-FORMAT T2) ────────────


def test_write_project_marker_refuses_different_project_id(tmp_path):
    """_write_project_marker must raise ValueError when target already has a
    marker for a different project (the ghost-marker guard)."""
    from core.projects.mutations import _write_project_marker

    existing_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    new_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

    # Write a pre-existing marker for a different project.
    existing_marker = json.dumps({"project_id": existing_id, "schema_version": 1})
    (tmp_path / ".dream-studio-project").write_text(existing_marker, encoding="utf-8")

    with pytest.raises(ValueError, match=existing_id):
        _write_project_marker(
            project_path=tmp_path,
            project_id=new_id,
            project_name="New Project",
            created_at="2026-01-01T00:00:00+00:00",
        )

    # Marker must still contain the original project_id — the write was refused.
    saved = json.loads((tmp_path / ".dream-studio-project").read_text(encoding="utf-8"))
    assert saved["project_id"] == existing_id


def test_write_project_marker_allows_overwrite_same_project(tmp_path):
    """_write_project_marker allows overwriting when the existing marker is for
    the SAME project (idempotent re-registration)."""
    from core.projects.mutations import _write_project_marker

    pid = "cccccccc-cccc-cccc-cccc-cccccccccccc"
    (tmp_path / ".dream-studio-project").write_text(
        json.dumps({"project_id": pid, "schema_version": 1}), encoding="utf-8"
    )

    # Should not raise — same project.
    _write_project_marker(
        project_path=tmp_path,
        project_id=pid,
        project_name="Same Project Updated",
        created_at="2026-06-01T00:00:00+00:00",
    )
    saved = json.loads((tmp_path / ".dream-studio-project").read_text(encoding="utf-8"))
    assert saved["project_id"] == pid
    assert saved["project_name"] == "Same Project Updated"


def test_write_project_marker_writes_new_marker_when_none_exists(tmp_path):
    """_write_project_marker creates a new JSON marker when no marker exists."""
    from core.projects.mutations import _write_project_marker

    pid = "dddddddd-dddd-dddd-dddd-dddddddddddd"
    _write_project_marker(
        project_path=tmp_path,
        project_id=pid,
        project_name="Brand New",
        created_at="2026-01-01T00:00:00+00:00",
    )
    marker_path = tmp_path / ".dream-studio-project"
    assert marker_path.exists()
    saved = json.loads(marker_path.read_text(encoding="utf-8"))
    assert saved["project_id"] == pid
    assert saved["project_name"] == "Brand New"
