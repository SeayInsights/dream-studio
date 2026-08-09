"""WO-CLIENT-DASHBOARD-API: the project-list API route surfaces client_id (data only — the
dashboard's client rollup view is a later Dashboard Coherence concern). Guarded so a pre-migration-
155 DB (no client_id column) returns client_id=None rather than erroring."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from core.config.sqlite_bootstrap import bootstrap_database
from projections.api.routes import project_list


def _seeded_conn(tmp_path: Path, *, client_id: str | None) -> sqlite3.Connection:
    db = tmp_path / "studio.db"
    bootstrap_database(db)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.execute(
        "INSERT INTO business_projects (project_id, name, status, created_at, updated_at,"
        " project_path, total_sessions, client_id) VALUES (?,?,?,?,?,?,?,?)",
        ("p1", "Acme", "active", "t", "t", r"C:\builds\acme", 3, client_id),
    )
    conn.commit()
    return conn


def _list(conn, monkeypatch) -> list[dict]:
    monkeypatch.setattr(project_list, "get_db_connection", lambda: conn)
    result = asyncio.run(project_list.list_projects(limit=50, offset=0))
    return result["projects"]


def test_project_list_surfaces_client_id(tmp_path, monkeypatch):
    conn = _seeded_conn(tmp_path, client_id="fulcrum")
    projects = _list(conn, monkeypatch)
    p1 = next((p for p in projects if p["project_id"] == "p1"), None)
    assert p1 is not None, "seeded project missing from the list response"
    assert p1["client_id"] == "fulcrum"


def test_project_list_client_id_null_when_unassigned(tmp_path, monkeypatch):
    conn = _seeded_conn(tmp_path, client_id=None)
    projects = _list(conn, monkeypatch)
    p1 = next((p for p in projects if p["project_id"] == "p1"), None)
    assert p1 is not None
    assert p1["client_id"] is None
