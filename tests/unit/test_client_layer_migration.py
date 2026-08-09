"""WO-CLIENT-SCHEMA: migration 155 adds the client layer (business_clients + project.client_id),
seeds the reference clients, the backfill classifies existing projects, and the paired rollback
removes it cleanly."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.clients.backfill import backfill_project_clients
from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]


def _bootstrap(tmp_path: Path) -> Path:
    db = tmp_path / "studio.db"
    bootstrap_database(db)
    return db


def test_fresh_bootstrap_has_client_layer(tmp_path: Path):
    conn = sqlite3.connect(str(_bootstrap(tmp_path)))
    try:
        ids = {r[0] for r in conn.execute("SELECT client_id FROM business_clients")}
        assert {"seayinsights", "fulcrum", "hypershift"} <= ids
        cols = {r[1] for r in conn.execute("PRAGMA table_info(business_projects)")}
        assert "client_id" in cols
    finally:
        conn.close()


def test_backfill_classifies_by_name_or_path(tmp_path: Path):
    conn = sqlite3.connect(str(_bootstrap(tmp_path)))
    try:
        conn.executemany(
            "INSERT INTO business_projects (project_id, name, status, created_at, updated_at,"
            " project_path) VALUES (?,?,?,?,?,?)",
            [
                ("p-ful", "Fulcrum Skill Library", "active", "t", "t", r"C:\Users\x\Fulcrum"),
                ("p-hyp", "Hypershift Ops", "active", "t", "t", None),
                ("p-ds", "Dream Studio", "paused", "t", "t", r"C:\x\dream-studio-clean"),
                ("p-path", "Some App", "active", "t", "t", r"C:\clients\hypershift\app"),
            ],
        )
        conn.commit()
        counts = backfill_project_clients(conn)
        conn.commit()
        got = {
            r[0]: r[1]
            for r in conn.execute(
                "SELECT project_id, client_id FROM business_projects WHERE project_id LIKE 'p-%'"
            )
        }
        assert got["p-ful"] == "fulcrum"
        assert got["p-hyp"] == "hypershift"
        assert got["p-ds"] == "seayinsights"  # catch-all
        assert got["p-path"] == "hypershift"  # matched on project_path
        assert counts["fulcrum"] == 1 and counts["hypershift"] == 2 and counts["seayinsights"] == 1
    finally:
        conn.close()


def test_backfill_is_idempotent(tmp_path: Path):
    conn = sqlite3.connect(str(_bootstrap(tmp_path)))
    try:
        conn.execute(
            "INSERT INTO business_projects (project_id, name, status, created_at, updated_at)"
            " VALUES ('p1', 'Acme', 'active', 't', 't')"
        )
        conn.commit()
        backfill_project_clients(conn)
        conn.commit()
        # A second run must not reassign an already-classified project.
        second = backfill_project_clients(conn)
        conn.commit()
        assert second == {"fulcrum": 0, "hypershift": 0, "seayinsights": 0}
        assert (
            conn.execute(
                "SELECT client_id FROM business_projects WHERE project_id='p1'"
            ).fetchone()[0]
            == "seayinsights"
        )
    finally:
        conn.close()


def test_rollback_removes_client_layer(tmp_path: Path):
    conn = sqlite3.connect(str(_bootstrap(tmp_path)))
    try:
        rollback = (
            REPO_ROOT / "core" / "event_store" / "migrations" / "rollback" / "155_client_layer.sql"
        ).read_text(encoding="utf-8")
        conn.executescript(rollback)
        conn.commit()
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "business_clients" not in tables
        cols = {r[1] for r in conn.execute("PRAGMA table_info(business_projects)")}
        assert "client_id" not in cols
    finally:
        conn.close()
