"""WO 35cb2edb: backfill historical pulse-*.md bodies into raw_operational_snapshots.report_body.

C4B-S4/S5 route new pulses into report_body and drop the disk write, but rows written before
migration 153 carry report_body=NULL with the body only in meta/pulse-<date>.md. backfill_report_bodies
migrates those into the column (UPDATE-only: never inserts, never overwrites an existing body).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.config.sqlite_bootstrap import bootstrap_database
from interfaces.cli.ds_analytics.backfill_pulse import backfill_report_bodies


def _seed_snapshot(db: Path, snapshot_date: str, project_slug: str, report_body=None) -> None:
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO raw_operational_snapshots"
        " (snapshot_date, project_slug, report_body, captured_at)"
        " VALUES (?, ?, ?, '2026-01-01T00:00:00Z')",
        (snapshot_date, project_slug, report_body),
    )
    conn.commit()
    conn.close()


def _report_body(db: Path, snapshot_date: str, project_slug: str):
    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            "SELECT report_body FROM raw_operational_snapshots"
            " WHERE snapshot_date = ? AND project_slug = ?",
            (snapshot_date, project_slug),
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def _write_pulse(meta: Path, date: str, body: str) -> None:
    meta.mkdir(parents=True, exist_ok=True)
    (meta / f"pulse-{date}.md").write_text(body, encoding="utf-8")


def test_backfills_null_body_rows_by_date(tmp_path: Path):
    db = tmp_path / "studio.db"
    bootstrap_database(db)
    meta = tmp_path / "meta"
    # Two rows share a date (two project_slugs) — both get the day's disk body.
    _seed_snapshot(db, "2026-05-17", "dream-studio-clean")
    _seed_snapshot(db, "2026-05-17", "Dannis Seay")
    _write_pulse(meta, "2026-05-17", "# Pulse 2026-05-17\n\nHEALTHY\n")

    updated = backfill_report_bodies(db_path=db, meta_dir=meta)

    assert updated == 2
    assert "HEALTHY" in _report_body(db, "2026-05-17", "dream-studio-clean")
    assert "HEALTHY" in _report_body(db, "2026-05-17", "Dannis Seay")


def test_does_not_overwrite_existing_body_or_touch_bodyless_dates(tmp_path: Path):
    db = tmp_path / "studio.db"
    bootstrap_database(db)
    meta = tmp_path / "meta"
    _seed_snapshot(db, "2026-05-18", "p", report_body="ORIGINAL")  # already has a body
    _seed_snapshot(db, "2026-05-19", "p")  # NULL, but no disk file for this date
    _write_pulse(meta, "2026-05-18", "NEW BODY")  # disk file exists but row already filled

    updated = backfill_report_bodies(db_path=db, meta_dir=meta)

    assert updated == 0  # existing body preserved; no disk file for the NULL date
    assert _report_body(db, "2026-05-18", "p") == "ORIGINAL"
    assert _report_body(db, "2026-05-19", "p") is None


def test_missing_meta_dir_is_a_noop(tmp_path: Path):
    db = tmp_path / "studio.db"
    bootstrap_database(db)
    assert backfill_report_bodies(db_path=db, meta_dir=tmp_path / "nope") == 0


def test_noop_when_report_body_column_absent(tmp_path: Path):
    """Simulate a pre-migration-153 DB: the table lacks report_body → no-op, no error."""
    db = tmp_path / "studio.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        "CREATE TABLE raw_operational_snapshots ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, snapshot_date TEXT NOT NULL,"
        " project_slug TEXT NOT NULL, captured_at TEXT NOT NULL,"
        " UNIQUE(snapshot_date, project_slug));"
    )
    conn.commit()
    conn.close()
    meta = tmp_path / "meta"
    _write_pulse(meta, "2026-05-17", "BODY")
    assert backfill_report_bodies(db_path=db, meta_dir=meta) == 0
