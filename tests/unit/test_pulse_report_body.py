"""WO-FILESDB-C4B S4: the full pulse report body is captured in the authority.

Migration 153 adds raw_operational_snapshots.report_body (nullable TEXT) so the FULL
pulse markdown lives in the DB, not only on disk (meta/pulse-<date>.md, dropped in C4B-5).
insert_operational_snapshot feature-detects the column so the live authority DB — where
153 is unreleased until `ds migrate activate` — keeps writing snapshots (sans body)
instead of erroring. These tests cover the migration, the round-trip, and that fallback.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.config.sqlite_bootstrap import bootstrap_database
from core.event_store.event_writer_buffer import insert_operational_snapshot

_PRE153_DDL = """
CREATE TABLE raw_operational_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    project_slug TEXT NOT NULL,
    ci_status TEXT,
    open_prs INTEGER,
    stale_branches INTEGER,
    pending_drafts INTEGER,
    open_escalations INTEGER,
    captured_at TEXT NOT NULL,
    UNIQUE(snapshot_date, project_slug)
);
"""


def _columns(db: Path) -> set[str]:
    conn = sqlite3.connect(str(db))
    try:
        return {r[1] for r in conn.execute("PRAGMA table_info(raw_operational_snapshots)")}
    finally:
        conn.close()


def test_migration_adds_report_body_column(tmp_path: Path):
    db = tmp_path / "studio.db"
    bootstrap_database(db)
    assert "report_body" in _columns(db)


def test_insert_stores_and_reads_back_full_body(tmp_path: Path):
    db = tmp_path / "studio.db"
    bootstrap_database(db)
    body = "# Pulse 2026-07-23\n\n### Open Escalations\n\n- ESC-RETRYCAP-abc12345\n"

    assert insert_operational_snapshot(
        "2026-07-23", "dream-studio-clean", open_escalations=1, report_body=body, db_path=db
    )

    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            "SELECT report_body, open_escalations FROM raw_operational_snapshots"
            " WHERE snapshot_date='2026-07-23' AND project_slug='dream-studio-clean'"
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == body
    assert row[1] == 1


def test_insert_without_body_leaves_column_null(tmp_path: Path):
    db = tmp_path / "studio.db"
    bootstrap_database(db)
    assert insert_operational_snapshot("2026-07-23", "p", db_path=db)
    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute("SELECT report_body FROM raw_operational_snapshots").fetchone()
    finally:
        conn.close()
    assert row[0] is None


def test_insert_falls_back_when_column_absent(tmp_path: Path):
    """Live-DB pre-release simulation: the pre-153 table has no report_body column, so
    the insert must still succeed (write the snapshot sans body) rather than raise."""
    db = tmp_path / "studio.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(_PRE153_DDL)
    conn.commit()
    conn.close()
    assert "report_body" not in _columns(db)

    # A report_body is passed but the column doesn't exist yet — must not error.
    assert insert_operational_snapshot(
        "2026-07-23", "p", open_prs=3, report_body="body ignored pre-release", db_path=db
    )

    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            "SELECT open_prs FROM raw_operational_snapshots WHERE snapshot_date='2026-07-23'"
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == 3  # snapshot still written, just without the body
