"""WS 8a-1 / 8b-1 — hook enforcement check unit tests.

Tests _enforcement_check() in emitters/claude_code/run.py directly.
No live config writes; DB interactions use in-process sqlite3.
Fail-open contract: any error must return None, never block execution.
Active project resolved from DB (not marker file) after WS 8b-1.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

import emitters.claude_code.run as run_module
import emitters.claude_code.project as project_module
from emitters.claude_code.run import _enforcement_check

PROJECT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
WO_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
WO_TITLE = "Build login form"


@pytest.fixture()
def minimal_db(tmp_path: Path) -> Path:
    """Minimal SQLite DB with business_projects + business_work_orders tables."""
    db = tmp_path / "studio.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE business_projects ("
        "project_id TEXT, name TEXT, description TEXT, "
        "status TEXT, created_at TEXT, updated_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE business_work_orders ("
        "work_order_id TEXT, project_id TEXT, title TEXT, "
        "work_order_type TEXT, status TEXT)"
    )
    conn.commit()
    conn.close()
    return db


@pytest.fixture()
def active_project_db(minimal_db: Path) -> Path:
    """minimal_db with an active project pre-seeded."""
    conn = sqlite3.connect(str(minimal_db))
    conn.execute(
        "INSERT INTO business_projects (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?, 'Test Project', '', 'active', "
        "'2026-05-16T00:00:00+00:00', '2026-05-16T00:00:00+00:00')",
        (PROJECT_ID,),
    )
    conn.commit()
    conn.close()
    return minimal_db


# ── no active project → no enforcement ───────────────────────────────────────


def test_no_active_project_returns_none(minimal_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No active project in DB → no project context → no enforcement."""
    monkeypatch.setattr(project_module, "_get_db_path", lambda: minimal_db)
    result = _enforcement_check()
    assert result is None


# ── in_progress work order → authorized ──────────────────────────────────────


def test_in_progress_work_order_returns_none(
    active_project_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Active in_progress work order → execution is authorized → return None."""
    conn = sqlite3.connect(str(active_project_db))
    conn.execute(
        "INSERT INTO business_work_orders (work_order_id, project_id, title, work_order_type, status)"
        " VALUES (?, ?, ?, ?, ?)",
        (WO_ID, PROJECT_ID, WO_TITLE, "ui_component", "in_progress"),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(project_module, "_get_db_path", lambda: active_project_db)
    result = _enforcement_check()
    assert result is None


# ── no in_progress + next open exists → blocking message ─────────────────────


@pytest.mark.xfail(
    reason="Slice 10: enforcement DB query not wired; _enforcement_check is a stub", strict=True
)
def test_no_in_progress_next_open_returns_message(
    active_project_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No in_progress WO; next open WO exists → blocking message with WO details."""
    conn = sqlite3.connect(str(active_project_db))
    conn.execute(
        "INSERT INTO business_work_orders (work_order_id, project_id, title, work_order_type, status)"
        " VALUES (?, ?, ?, ?, ?)",
        (WO_ID, PROJECT_ID, WO_TITLE, "ui_component", "open"),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(project_module, "_get_db_path", lambda: active_project_db)
    result = _enforcement_check()

    assert result is not None
    assert WO_ID in result
    assert WO_TITLE in result
    assert "work-order start" in result
    assert "Do not write" in result


# ── no work orders at all → scoping message ──────────────────────────────────


@pytest.mark.xfail(
    reason="Slice 10: enforcement DB query not wired; _enforcement_check is a stub", strict=True
)
def test_no_work_orders_returns_scoping_message(
    active_project_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No work orders at all → message directing to project next / scope."""
    monkeypatch.setattr(project_module, "_get_db_path", lambda: active_project_db)
    result = _enforcement_check()

    assert result is not None
    assert PROJECT_ID in result
    assert "project next" in result
    assert "scope" in result


# ── DB failure → fail open ────────────────────────────────────────────────────


def test_db_missing_returns_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """DB file not found → fail open → return None."""
    monkeypatch.setattr(project_module, "_get_db_path", lambda: tmp_path / "no.db")
    result = _enforcement_check()
    assert result is None


def test_db_corrupt_returns_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """DB exists but is not valid SQLite → fail open → return None."""
    bad_db = tmp_path / "bad.db"
    bad_db.write_text("not a database")
    monkeypatch.setattr(project_module, "_get_db_path", lambda: bad_db)
    result = _enforcement_check()
    assert result is None


# ── hook return format ────────────────────────────────────────────────────────


@pytest.mark.xfail(
    reason="Slice 10: enforcement DB query not wired; _enforcement_check is a stub", strict=True
)
def test_blocking_message_is_valid_json_envelope(
    active_project_db: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """When enforcement triggers, main() prints JSON with type and content keys."""
    import io

    conn = sqlite3.connect(str(active_project_db))
    conn.execute(
        "INSERT INTO business_work_orders (work_order_id, project_id, title, work_order_type, status)"
        " VALUES (?, ?, ?, ?, ?)",
        (WO_ID, PROJECT_ID, WO_TITLE, "ui_component", "open"),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(project_module, "_get_db_path", lambda: active_project_db)
    monkeypatch.setattr(run_module, "_get_plugin_root", lambda: Path(__file__).resolve().parents[2])

    old_stdin = sys.stdin
    sys.stdin = io.StringIO('{"session_id": "test", "prompt": "do work"}')
    old_argv = sys.argv[:]
    sys.argv = ["run.py", "UserPromptSubmit"]
    try:
        run_module.main()
    except Exception:
        pass
    finally:
        sys.stdin = old_stdin
        sys.argv = old_argv

    out = capsys.readouterr().out.strip()
    assert out, "Expected JSON output but got empty stdout"
    parsed = json.loads(out)
    assert parsed.get("type") == "message"
    assert "content" in parsed
    assert WO_ID in parsed["content"]
