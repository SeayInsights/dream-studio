"""Coverage for core.analytics.duckdb_store.derive_events_fact.

derive_events_fact builds the wide events_fact in DuckDB from the SQLite dual
canonical events (ai_canonical_events + business_canonical_events). The runner is
the sole writer; SQLite is read-only NEVER-AUTHORITY. The derivation is
incremental by event_timestamp unless full_rebuild=True, and returns the number
of rows written.

WO 15945624: this foundation function previously had no test coverage.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.analytics.duckdb_store import (
    connect_analytics,
    derive_events_fact,
    ensure_analytics_schema,
)


def _seed_studio_db(path: Path) -> None:
    """Create a SQLite studio.db with the two canonical event tables seeded."""
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript("""
            CREATE TABLE ai_canonical_events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                event_timestamp TEXT NOT NULL,
                payload TEXT NOT NULL,
                session_id TEXT,
                model_id TEXT,
                project_id TEXT,
                severity TEXT
            );
            CREATE TABLE business_canonical_events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                event_timestamp TEXT NOT NULL,
                payload TEXT NOT NULL,
                project_id TEXT,
                milestone_id TEXT,
                severity TEXT
            );
            """)
        conn.execute(
            "INSERT INTO ai_canonical_events VALUES (?,?,?,?,?,?,?,?)",
            (
                "ai-1",
                "token.consumed",
                "2026-01-01T00:00:00Z",
                json.dumps({"input_tokens": 100, "output_tokens": 40, "status": "ok"}),
                "sess-1",
                "sonnet",
                "proj-a",
                "info",
            ),
        )
        conn.execute(
            "INSERT INTO ai_canonical_events VALUES (?,?,?,?,?,?,?,?)",
            (
                "ai-2",
                "execution.completed",
                "2026-01-02T00:00:00Z",
                json.dumps({"duration_ms": 1500, "exit_code": 0, "outcome_status": "completed"}),
                "sess-2",
                "haiku",
                "proj-a",
                "info",
            ),
        )
        conn.execute(
            "INSERT INTO business_canonical_events VALUES (?,?,?,?,?,?,?)",
            (
                "biz-1",
                "work_order.started",
                "2026-01-03T00:00:00Z",
                json.dumps({"status": "active"}),
                "proj-a",
                "ms-1",
                "info",
            ),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def studio_db(tmp_path: Path) -> Path:
    path = tmp_path / "studio.db"
    _seed_studio_db(path)
    return path


@pytest.fixture
def duck(tmp_path: Path):
    conn = connect_analytics(tmp_path / "aggregate_metrics.db", read_only=False)
    ensure_analytics_schema(conn)
    yield conn
    conn.close()


def test_derives_all_canonical_rows(studio_db, duck):
    written = derive_events_fact(duck, str(studio_db))
    assert written == 3  # 2 ai + 1 business

    total = duck.execute("SELECT COUNT(*) FROM events_fact").fetchone()[0]
    assert total == 3

    by_source = dict(
        duck.execute("SELECT source, COUNT(*) FROM events_fact GROUP BY source").fetchall()
    )
    assert by_source == {"ai": 2, "business": 1}


def test_extracts_payload_and_dimension_columns(studio_db, duck):
    derive_events_fact(duck, str(studio_db))

    # Payload-extracted metric columns
    row = duck.execute(
        "SELECT input_tokens, output_tokens, status FROM events_fact WHERE event_id = 'ai-1'"
    ).fetchone()
    assert row == (100, 40, "ok")

    # duration_ms / exit_code / outcome (from payload $.outcome_status) on ai-2
    row2 = duck.execute(
        "SELECT duration_ms, exit_code, outcome FROM events_fact WHERE event_id = 'ai-2'"
    ).fetchone()
    assert row2 == (1500, 0, "completed")

    # Dimension columns present on the SQLite source are mapped through
    model = duck.execute("SELECT model_id FROM events_fact WHERE event_id = 'ai-1'").fetchone()[0]
    assert model == "sonnet"
    milestone = duck.execute(
        "SELECT milestone_id FROM events_fact WHERE event_id = 'biz-1'"
    ).fetchone()[0]
    assert milestone == "ms-1"


def test_incremental_skips_already_derived_rows(studio_db, duck):
    assert derive_events_fact(duck, str(studio_db)) == 3
    # Second pass with no new source rows derives nothing (incremental by timestamp).
    assert derive_events_fact(duck, str(studio_db)) == 0
    assert duck.execute("SELECT COUNT(*) FROM events_fact").fetchone()[0] == 3


def test_incremental_picks_up_new_rows(studio_db, duck):
    assert derive_events_fact(duck, str(studio_db)) == 3

    conn = sqlite3.connect(str(studio_db))
    try:
        conn.execute(
            "INSERT INTO ai_canonical_events VALUES (?,?,?,?,?,?,?,?)",
            (
                "ai-3",
                "token.consumed",
                "2026-02-01T00:00:00Z",  # newer than the max derived timestamp
                json.dumps({"input_tokens": 7}),
                "sess-3",
                "opus",
                "proj-a",
                "info",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    assert derive_events_fact(duck, str(studio_db)) == 1
    assert duck.execute("SELECT COUNT(*) FROM events_fact").fetchone()[0] == 4


def test_full_rebuild_replaces_all_rows(studio_db, duck):
    assert derive_events_fact(duck, str(studio_db)) == 3
    # full_rebuild clears events_fact then re-derives every source row.
    assert derive_events_fact(duck, str(studio_db), full_rebuild=True) == 3
    assert duck.execute("SELECT COUNT(*) FROM events_fact").fetchone()[0] == 3
