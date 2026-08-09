"""WO-CLIENT-SCHEMA: migration 155 adds the client layer (business_clients + project.client_id),
seeds the three reference clients, and the paired rollback removes it cleanly.

Scope note: assigning existing projects to a client (the backfill) is done EVENT-SOURCED by the
client engine (WO-CLIENT-ENGINE), not by a direct read-model UPDATE — so it is tested there, not
here. This work order is the additive schema + reference-data seed + reversibility only.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

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


def test_seed_clients_have_names(tmp_path: Path):
    conn = sqlite3.connect(str(_bootstrap(tmp_path)))
    try:
        names = {r[0]: r[1] for r in conn.execute("SELECT client_id, name FROM business_clients")}
        assert names["seayinsights"] == "SeayInsights"
        assert names["fulcrum"] == "Fulcrum"
        assert names["hypershift"] == "Hypershift"
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
