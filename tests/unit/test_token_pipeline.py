"""Tests for WO-TOKEN-PIPELINE: token_usage_sql falls back to ai_canonical_events.

Verifies:
  - token_usage_sql returns canonical_events fallback when token_usage_records is empty
  - token_usage_sql uses token_usage_records (primary) when it has rows
  - TokenCollector.collect returns a non-empty timeline from canonical_events fallback
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from projections.core.collectors.authority_sources import token_usage_sql
from projections.core.collectors.token_collector import TokenCollector

_TOKEN_USAGE_RECORDS_DDL = """
CREATE TABLE token_usage_records (
    token_usage_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    process_run_id TEXT,
    agent_id TEXT,
    skill_id TEXT,
    workflow_id TEXT,
    hook_id TEXT,
    model_id TEXT,
    provider TEXT,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_cost NUMERIC(20, 8) NOT NULL DEFAULT 0,
    purpose TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    adapter_id TEXT,
    billing_mode TEXT NOT NULL DEFAULT 'unknown',
    token_visibility TEXT NOT NULL DEFAULT 'exact',
    cost_visibility TEXT NOT NULL DEFAULT 'unknown',
    usage_source TEXT NOT NULL DEFAULT 'local_telemetry',
    cost_source TEXT NOT NULL DEFAULT 'unknown',
    accounting_confidence TEXT NOT NULL DEFAULT 'medium',
    cache_read_tokens INTEGER NOT NULL DEFAULT 0
)
"""

_AI_CANONICAL_EVENTS_DDL = """
CREATE TABLE ai_canonical_events (
    event_id TEXT PRIMARY KEY,
    received_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_timestamp TEXT,
    schema_version INTEGER,
    trace TEXT,
    payload TEXT,
    correlation_id TEXT,
    session_id TEXT,
    skill_id TEXT,
    workflow_id TEXT,
    agent_id TEXT,
    hook_id TEXT,
    model_id TEXT,
    severity TEXT,
    source TEXT
)
"""


def _seed_canonical_token_events(conn: sqlite3.Connection, count: int = 3) -> None:
    for i in range(count):
        payload = json.dumps(
            {
                "input_tokens": 1000 + i * 100,
                "output_tokens": 500 + i * 50,
                "cache_read_input_tokens": 0,
                "model": "claude-sonnet-4-6",
                "granularity": "tool_invocation",
            }
        )
        trace = json.dumps({"project_id": "proj-test-abc", "session_id": f"sess-{i}"})
        conn.execute(
            "INSERT INTO ai_canonical_events"
            "(event_id, received_at, event_type, payload, trace, session_id, model_id)"
            " VALUES (?, datetime('now', ?), 'token.consumed', ?, ?, ?, ?)",
            (
                f"evt-tok-{i}",
                f"-{i} days",
                payload,
                trace,
                f"sess-{i}",
                "claude-sonnet-4-6",
            ),
        )
    conn.commit()


def _db_empty_records_with_canonical(tmp_path: Path) -> Path:
    db_path = tmp_path / "tok-canonical.db"
    conn = sqlite3.connect(db_path)
    conn.execute(_TOKEN_USAGE_RECORDS_DDL)
    conn.execute(_AI_CANONICAL_EVENTS_DDL)
    # token_usage_records stays empty; canonical has 3 events
    _seed_canonical_token_events(conn)
    conn.close()
    return db_path


def _db_primary_records_populated(tmp_path: Path) -> Path:
    db_path = tmp_path / "tok-primary.db"
    conn = sqlite3.connect(db_path)
    conn.execute(_TOKEN_USAGE_RECORDS_DDL)
    conn.execute(_AI_CANONICAL_EVENTS_DDL)
    # Populate token_usage_records (primary should win)
    conn.execute(
        "INSERT INTO token_usage_records"
        "(token_usage_id, model_id, input_tokens, output_tokens, total_tokens, estimated_cost, created_at)"
        " VALUES ('tur-1', 'claude-sonnet-4-6', 2000, 800, 2800, 0, datetime('now'))"
    )
    # Also seed canonical — should be suppressed once primary has rows
    _seed_canonical_token_events(conn)
    conn.commit()
    conn.close()
    return db_path


def test_token_usage_sql_falls_back_to_canonical_events_when_records_empty(tmp_path):
    db_path = _db_empty_records_with_canonical(tmp_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        sql = token_usage_sql(conn)
        assert sql is not None, "token_usage_sql should return non-None when canonical events exist"
        rows = conn.execute(f"SELECT * FROM ({sql}) t").fetchall()
        assert len(rows) == 3, f"Expected 3 rows from canonical fallback, got {len(rows)}"
        models = {r["model"] for r in rows}
        assert "claude-sonnet-4-6" in models
    finally:
        conn.close()


def test_token_usage_sql_uses_primary_when_records_populated(tmp_path):
    db_path = _db_primary_records_populated(tmp_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        sql = token_usage_sql(conn)
        assert sql is not None
        assert "token_usage_records" in sql, "Primary path should read from token_usage_records"
        assert "ai_canonical_events" not in sql, "Primary path must not mix in canonical_events"
        rows = conn.execute(f"SELECT * FROM ({sql}) t").fetchall()
        assert len(rows) == 1
        assert rows[0]["input_tokens"] == 2000
    finally:
        conn.close()


def test_token_usage_sql_canonical_rows_have_correct_shape(tmp_path):
    db_path = _db_empty_records_with_canonical(tmp_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        sql = token_usage_sql(conn)
        assert sql is not None
        rows = conn.execute(f"SELECT * FROM ({sql}) t").fetchall()
        assert len(rows) > 0
        row = rows[0]
        # Verify all required dashboard columns are present
        assert row["input_tokens"] > 0
        assert row["output_tokens"] > 0
        assert row["total_tokens"] == row["input_tokens"] + row["output_tokens"]
        assert row["model"] == "claude-sonnet-4-6"
        assert row["usage_source"] == "canonical_events"
        assert row["recorded_at"] is not None
    finally:
        conn.close()


def test_collector_returns_nonempty_timeline_from_canonical_fallback(tmp_path):
    db_path = _db_empty_records_with_canonical(tmp_path)
    collector = TokenCollector(db_path=str(db_path))
    result = collector.collect(days=30)
    assert result["total_tokens"] > 0, "Expected non-zero total_tokens from canonical fallback"
    assert "claude-sonnet-4-6" in result["by_model"], "Expected model entry from canonical events"
    assert len(result["timeline"]) > 0, "Expected non-empty timeline"
