"""WO-TOKEN-CAPTURE-REAL: the Stop handler emits real per-turn token.consumed from the
session transcript, so token_usage_records reflects true usage (not the ~364k noise).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from emitters.claude_code.token_transcript import normalize_stop_token_usage


def _write_transcript(tmp_path: Path) -> Path:
    """A transcript with 2 real assistant turns, 1 zero-usage turn, 1 user line."""
    lines = [
        {"type": "user", "uuid": "u0", "message": {"role": "user"}},
        {
            "type": "assistant",
            "uuid": "a1",
            "message": {
                "id": "m1",
                "model": "claude-sonnet-4-6",
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 500,
                    "cache_creation_input_tokens": 200,
                    "cache_read_input_tokens": 8000,
                },
            },
        },
        {
            "type": "assistant",
            "uuid": "a2",
            "message": {
                "id": "m2",
                "model": "claude-sonnet-4-6",
                "usage": {"input_tokens": 300, "output_tokens": 700},
            },
        },
        {  # zero-usage assistant turn — skipped
            "type": "assistant",
            "uuid": "a3",
            "message": {"id": "m3", "model": "claude-sonnet-4-6", "usage": {"input_tokens": 0}},
        },
    ]
    path = tmp_path / "transcript.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    return path


def test_emits_token_consumed_per_turn(tmp_path, spool_root):
    transcript = _write_transcript(tmp_path)
    envs = normalize_stop_token_usage({"transcript_path": str(transcript)}, root=spool_root)
    assert [e.event_type for e in envs] == ["token.consumed", "token.consumed"]
    first = envs[0]
    assert first.payload["input_tokens"] == 1000
    assert first.payload["output_tokens"] == 500
    assert first.payload["cache_creation_input_tokens"] == 200
    assert first.payload["cache_read_input_tokens"] == 8000
    assert first.payload["model"] == "claude-sonnet-4-6"
    assert first.trace["model_id"] == "claude-sonnet-4-6"


def test_event_ids_are_deterministic_for_dedup(tmp_path, spool_root):
    """Deterministic event_id (tok-<uuid>) makes re-emission idempotent at ingest."""
    transcript = _write_transcript(tmp_path)
    ids_1 = [e.event_id for e in normalize_stop_token_usage({"transcript_path": str(transcript)})]
    ids_2 = [e.event_id for e in normalize_stop_token_usage({"transcript_path": str(transcript)})]
    assert ids_1 == ["tok-a1", "tok-a2"]
    assert ids_1 == ids_2  # stable across Stop invocations


def test_missing_transcript_is_safe(spool_root):
    assert normalize_stop_token_usage({}) == []
    assert normalize_stop_token_usage({"transcript_path": "/no/such/file.jsonl"}) == []


def test_round_trip_populates_token_usage_records(tmp_path, spool_root):
    """End-to-end: transcript -> token.consumed -> ingest -> DuckDB token_usage_records
    sums the real per-turn tokens (1000+500 + 300+700 = 2500)."""
    from core.analytics import duckdb_store
    from core.config.sqlite_bootstrap import bootstrap_database
    from spool.ingestor import ingest
    from spool.writer import write_event

    transcript = _write_transcript(tmp_path)
    studio_db = spool_root / "studio.db"
    bootstrap_database(
        studio_db
    )  # full canonical schema so derive_events_fact sees every source table
    envs = normalize_stop_token_usage({"transcript_path": str(transcript)}, root=spool_root)
    for env in envs:
        write_event(env.to_dict(), root=spool_root)
    # Re-emit once more to prove idempotency (same event_ids -> INSERT OR IGNORE).
    for env in normalize_stop_token_usage({"transcript_path": str(transcript)}, root=spool_root):
        write_event(env.to_dict(), root=spool_root)
    result = ingest(root=spool_root, db_path=studio_db)
    assert result.failed == 0

    rows = (
        sqlite3.connect(str(studio_db))
        .execute("SELECT COUNT(*) FROM ai_canonical_events WHERE event_type='token.consumed'")
        .fetchone()[0]
    )
    assert rows == 2, "two turns, deduped despite the double emit"

    conn = duckdb_store.connect_analytics(spool_root / "aggregate_metrics.db", read_only=False)
    try:
        duckdb_store.ensure_analytics_schema(conn)
        duckdb_store.derive_events_fact(conn, str(studio_db))
        total = conn.execute("SELECT SUM(total_tokens) FROM token_usage_records").fetchone()[0]
    finally:
        conn.close()
    assert total == 2500, f"token_usage_records must sum real per-turn tokens, got {total}"
