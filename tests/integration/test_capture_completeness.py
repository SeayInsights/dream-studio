"""WO-CAPTURE-COMPLETENESS T5: end-to-end capture → projection completeness.

Proves the forward fix: a PostToolUse payload that omits ``model`` (the main-loop
case) still produces a token.consumed envelope carrying the real model, recovered
from the session transcript, and that model materializes into
token_usage_records.model_id through the projection. Also pins the
payload-supplied model (subagent case) and the honest NULL when no source exists.

This is the live-path proof for T2 (model captured) that the rescoped, post-fix
SQL-CHECK guards going forward.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _write_transcript(path: Path, model: str) -> None:
    """Write a minimal session transcript JSONL whose last assistant turn names *model*."""
    lines = [
        {"type": "user", "message": {"role": "user", "content": "hi"}},
        {
            "type": "assistant",
            "message": {"role": "assistant", "model": "<synthetic>", "content": "warmup"},
        },
        {
            "type": "assistant",
            "message": {"role": "assistant", "model": model, "content": "real turn"},
        },
    ]
    path.write_text("\n".join(json.dumps(line) for line in lines), encoding="utf-8")


def _capture_envelope(payload: dict, monkeypatch):
    """Drive handle_post_tool_use and return the single spooled envelope."""
    import core.telemetry.token_capture as tc

    captured: list = []
    monkeypatch.setattr(tc._spool_writer_mod, "write_envelopes", lambda envs: captured.extend(envs))
    tc.handle_post_tool_use(payload)
    assert len(captured) == 1, f"expected exactly one spooled envelope, got {len(captured)}"
    return captured[0]


def _base_payload(transcript_path: Path | None = None, model: str | None = None) -> dict:
    payload = {
        "session_id": "sess-capture-complete-01",
        "tool_name": "Bash",
        "tool_use_id": "toolu_" + uuid.uuid4().hex[:16],
        "usage": {
            "input_tokens": 1200,
            "output_tokens": 340,
            "cache_creation_input_tokens": 50,
            "cache_read_input_tokens": 80,
        },
    }
    if transcript_path is not None:
        payload["transcript_path"] = str(transcript_path)
    if model is not None:
        payload["model"] = model
    return payload


def test_model_recovered_from_transcript_when_payload_omits_it(tmp_path, monkeypatch):
    """Main-loop case: payload has no model; the issuing turn's model is recovered
    from transcript_path and carried on the token.consumed envelope."""
    transcript = tmp_path / "session.jsonl"
    _write_transcript(transcript, "claude-opus-4-8")
    env = _capture_envelope(_base_payload(transcript_path=transcript), monkeypatch)
    assert env.payload.get("model") == "claude-opus-4-8"


def test_payload_model_takes_precedence(tmp_path, monkeypatch):
    """Subagent case: an explicit payload.model wins over the transcript."""
    transcript = tmp_path / "session.jsonl"
    _write_transcript(transcript, "claude-opus-4-8")
    env = _capture_envelope(
        _base_payload(transcript_path=transcript, model="claude-sonnet-4-6"), monkeypatch
    )
    assert env.payload.get("model") == "claude-sonnet-4-6"


def test_model_null_when_no_source(tmp_path, monkeypatch):
    """No payload model and no transcript → model stays absent (honest NULL, never a placeholder)."""
    env = _capture_envelope(_base_payload(), monkeypatch)
    assert "model" not in env.payload


def test_end_to_end(tmp_path, monkeypatch):
    """Capture (transcript model recovery) → canonical event → DuckDB events_fact
    → token_usage_records view .model_id.

    A main-loop token event with no payload model produces a row whose model_id is
    the real model from the transcript — closing the cost-by-model gap going forward.

    WO-DBA-DROP (migration 137): core/projections/token_projection.py and the
    SQLite token_usage_records table it materialized into are both retired.
    The read side is now the DuckDB aggregate_metrics.db token_usage_records
    view over events_fact (core/analytics/duckdb_store.py), fed by the real
    derive_events_fact() projector — exercised directly here rather than via
    the retired SQLite-to-SQLite projection.
    """
    from core.analytics.duckdb_store import (
        connect_analytics,
        derive_events_fact,
        ensure_analytics_schema,
    )
    from core.config.sqlite_bootstrap import bootstrap_database

    db_path = tmp_path / "state" / "studio.db"
    bootstrap_database(db_path)

    transcript = tmp_path / "session.jsonl"
    _write_transcript(transcript, "claude-opus-4-8")
    env = _capture_envelope(_base_payload(transcript_path=transcript), monkeypatch)

    # Land the spooled envelope in the canonical events table (the step the
    # real spool ingestor performs), then run the real DuckDB projector.
    event = env.to_dict()
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO ai_canonical_events"
            " (event_id, event_type, event_timestamp, session_id, trace, payload)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                event["event_id"],
                event["event_type"],
                event["timestamp"],
                event["session_id"],
                json.dumps(event["trace"]),
                json.dumps(event["payload"]),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    analytics_db = tmp_path / "aggregate_metrics.db"
    duck_conn = connect_analytics(analytics_db, read_only=False)
    try:
        ensure_analytics_schema(duck_conn)
        written = derive_events_fact(duck_conn, str(db_path), full_rebuild=True)
        assert written == 1, "derive_events_fact must materialize exactly one row"
        row = duck_conn.execute(
            "SELECT model_id, input_tokens, output_tokens FROM token_usage_records"
            " WHERE token_usage_id = ?",
            [event["event_id"]],
        ).fetchone()
    finally:
        duck_conn.close()

    assert row is not None, "token_usage_records view must carry the captured event"
    assert row[0] == "claude-opus-4-8", "model_id must be the transcript-recovered model"
    assert row[1] == 1200
    assert row[2] == 340
