"""Tests for no-marker attribution (Part A).

Three cases, per WO:
  1. Persistent repo (marker present) → resolves via marker
  2. One-time repo (no marker, registered by path) → resolves via project_path SQLite
  3. Unregistered (neither) → None, no throw

The hot-path no-throw discipline from A2 must hold for all three.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path

import pytest

# ── Test 1: marker present → resolves via marker ─────────────────────────────


def test_marker_resolution_returns_uuid(tmp_path, monkeypatch):
    """Persistent repo (marker present) resolves via marker."""
    monkeypatch.setenv("DS_CWD_RESOLVER_ROOT", str(tempfile.gettempdir()))
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(tmp_path / "test.db"))

    test_uuid = str(uuid.uuid4())
    marker = tmp_path / ".dream-studio-project"
    marker.write_text(
        json.dumps({"schema_version": 1, "project_id": test_uuid, "project_name": "Test"}),
        encoding="utf-8",
    )

    os.chdir(str(tmp_path))
    from core.sdlc.cwd_resolver import resolve_project_from_cwd

    ctx = resolve_project_from_cwd()
    assert ctx is not None
    assert ctx.project_id == test_uuid
    assert ctx.marker_format == "json"
    assert ctx.marker_path is not None


# ── Test 2: no marker, registered by path → SQLite fallback ─────────────────


def test_no_marker_project_path_fallback(tmp_path, monkeypatch):
    """No-marker repo registered by path resolves via SQLite project_path lookup."""
    import sqlite3

    monkeypatch.setenv("DS_CWD_RESOLVER_ROOT", str(tempfile.gettempdir()))
    db_path = tmp_path / "test_state" / "studio.db"
    db_path.parent.mkdir(parents=True)
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_path))

    # Build a minimal schema
    conn = sqlite3.connect(str(db_path))
    conn.execute("""CREATE TABLE business_projects (
            project_id TEXT PRIMARY KEY, name TEXT, description TEXT,
            status TEXT, project_path TEXT, created_at TEXT, updated_at TEXT
        )""")
    test_uuid = str(uuid.uuid4())
    repo_dir = tmp_path / "myrepo"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()  # simulate git repo root
    conn.execute(
        "INSERT INTO business_projects VALUES (?, ?, '', 'active', ?, '2026-01-01', '2026-01-01')",
        (test_uuid, "MyRepo", str(repo_dir.resolve())),
    )
    conn.commit()
    conn.close()

    os.chdir(str(repo_dir))
    # Reload module to clear any cached state
    import importlib, core.sdlc.cwd_resolver as mod

    importlib.reload(mod)
    ctx = mod.resolve_project_from_cwd()

    assert ctx is not None, "SQLite fallback should resolve no-marker repo via project_path"
    assert ctx.project_id == test_uuid
    assert ctx.marker_format == "project_path"
    assert ctx.marker_path is None


# ── Test 3: unregistered → None, no throw ────────────────────────────────────


def test_unregistered_returns_none_no_throw(tmp_path, monkeypatch):
    """Unregistered directory (no marker, not in DB) → None, never throws."""
    monkeypatch.setenv("DS_CWD_RESOLVER_ROOT", str(tempfile.gettempdir()))
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(tmp_path / "nonexistent.db"))

    try:
        os.chdir(str(tmp_path))
        from core.sdlc.cwd_resolver import resolve_project_from_cwd

        result = resolve_project_from_cwd()
        assert result is None, "Unregistered directory must return None, not raise"
    except Exception as e:
        pytest.fail(f"resolve_project_from_cwd raised an exception on unregistered dir: {e!r}")
    finally:
        os.chdir(str(Path(__file__).parents[2]))


# ── Test 4: resolve_project_from_path function directly ──────────────────────


def test_resolve_project_from_path_found(tmp_path, monkeypatch):
    """resolve_project_from_path returns context when path is registered."""
    import sqlite3

    db_path = tmp_path / "state" / "studio.db"
    db_path.parent.mkdir()
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_path))

    conn = sqlite3.connect(str(db_path))
    conn.execute("""CREATE TABLE business_projects (
            project_id TEXT PRIMARY KEY, name TEXT, description TEXT,
            status TEXT, project_path TEXT, created_at TEXT, updated_at TEXT
        )""")
    test_uuid = str(uuid.uuid4())
    repo_dir = (tmp_path / "repo").resolve()
    repo_dir.mkdir()
    conn.execute(
        "INSERT INTO business_projects VALUES (?, 'Repo', '', 'active', ?, '2026-01-01', '2026-01-01')",
        (test_uuid, str(repo_dir)),
    )
    conn.commit()
    conn.close()

    import importlib, core.sdlc.cwd_resolver as mod

    importlib.reload(mod)
    ctx = mod.resolve_project_from_path(repo_dir)

    assert ctx is not None
    assert ctx.project_id == test_uuid
    assert ctx.marker_format == "project_path"
    assert ctx.marker_path is None


def test_resolve_project_from_path_not_found(tmp_path, monkeypatch):
    """resolve_project_from_path returns None for unregistered path."""
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(tmp_path / "notexist.db"))

    from core.sdlc.cwd_resolver import resolve_project_from_path

    result = resolve_project_from_path(tmp_path / "notregistered")
    assert result is None


# ── Test 5: write_marker=False default in register_project ───────────────────


def test_register_project_no_marker_default(tmp_path, monkeypatch):
    """register_project with write_marker=False does not create marker file."""
    import sqlite3

    db_path = tmp_path / "state" / "studio.db"
    db_path.parent.mkdir()
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_path))

    # Minimal DB setup
    conn = sqlite3.connect(str(db_path))
    conn.execute("""CREATE TABLE business_projects (
            project_id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
            status TEXT NOT NULL DEFAULT 'active', project_path TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            source_event_id TEXT, last_event_id TEXT,
            total_sessions INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            last_session_at TEXT,
            detected_stack TEXT, stack_json TEXT
        )""")
    conn.commit()
    conn.close()

    repo_dir = tmp_path / "target_repo"
    repo_dir.mkdir()

    from core.projects.mutations import register_project

    result = register_project(
        name="TestRepo",
        project_path=repo_dir,
        write_marker=False,
        source_root=tmp_path,
    )

    assert result["ok"] is True
    assert result["marker_written"] is False
    assert not (repo_dir / ".dream-studio-project").exists(), "No marker should be written"
