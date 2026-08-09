"""WO-CLIENT-DASHBOARD-API: the project-list API route surfaces client_id and supports the optional
?client=<id> filter (data only — the dashboard's visual client rollup is a later Dashboard
Coherence concern). Assertions go through the real async route against a seeded DB.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from core.config.sqlite_bootstrap import bootstrap_database
from projections.api.routes import project_list


def _seed_two_clients(tmp_path: Path) -> Path:
    db = tmp_path / "studio.db"
    bootstrap_database(db)
    conn = sqlite3.connect(str(db))
    try:
        conn.executemany(
            "INSERT INTO business_projects (project_id, name, status, created_at, updated_at,"
            " project_path, total_sessions, client_id) VALUES (?,?,?,?,?,?,?,?)",
            [
                ("p-ful", "Fulcrum App", "active", "t", "t", r"C:\b\ful", 2, "fulcrum"),
                ("p-sea", "Studio", "active", "t", "t", r"C:\b\sea", 2, "seayinsights"),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return db


def _fresh(db: Path) -> sqlite3.Connection:
    # The route closes its connection in a finally, so every call needs a fresh one.
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    return conn


def _list(db: Path, monkeypatch, **kw) -> list[dict]:
    monkeypatch.setattr(project_list, "get_db_connection", lambda: _fresh(db))
    return asyncio.run(project_list.list_projects(limit=50, offset=0, **kw))["projects"]


def test_project_list_surfaces_client_id(tmp_path, monkeypatch):
    """A returned project row carries its client_id (the new dashboard-API field)."""
    db = _seed_two_clients(tmp_path)
    projects = _list(db, monkeypatch, client="fulcrum")
    assert [p["project_id"] for p in projects] == ["p-ful"]
    assert projects[0]["client_id"] == "fulcrum"


def test_project_list_client_filter_scopes_to_one_client(tmp_path, monkeypatch):
    """?client=<id> returns only that client's projects."""
    db = _seed_two_clients(tmp_path)
    sea = _list(db, monkeypatch, client="seayinsights")
    assert [p["project_id"] for p in sea] == ["p-sea"]
    assert sea[0]["client_id"] == "seayinsights"
    # A client with no projects returns an empty list (not an error).
    assert _list(db, monkeypatch, client="hypershift") == []


def test_project_list_client_id_guarded_when_column_absent(tmp_path, monkeypatch):
    """Guard: on a DB without the migration-155 client_id column, the route must not error — the
    client_id expr falls back to NULL. Simulated by applying the paired rollback."""
    db = tmp_path / "studio.db"
    bootstrap_database(db)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rollback = (
        Path(project_list.__file__).resolve().parents[3]
        / "core"
        / "event_store"
        / "migrations"
        / "rollback"
        / "155_client_layer.sql"
    ).read_text(encoding="utf-8")
    conn.executescript(rollback)  # drops business_projects.client_id + business_clients
    conn.commit()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(business_projects)")}
    assert "client_id" not in cols
    conn.close()
    # The route builds a guarded 'NULL AS client_id' expr and must not raise.
    monkeypatch.setattr(project_list, "get_db_connection", lambda: _fresh(db))
    result = asyncio.run(project_list.list_projects(limit=50, offset=0))
    assert result["total"] == 0 or all(p.get("client_id") is None for p in result["projects"])
