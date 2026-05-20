from __future__ import annotations
import json
import sqlite3
import pytest


def test_ingestor_reads_spool_writes_sqlite(spool_root):
    """Ingestor reads from temp spool, writes to test SQLite DB, assert canonical_events row."""
    from spool.writer import write_event
    from spool.ingestor import ingest

    db_path = spool_root / "studio.db"
    envelope = {
        "event_id": "int-test-001",
        "event_type": "prompt.lifecycle.submitted",
        "timestamp": "2026-05-15T12:00:00+00:00",
        "schema_version": 1,
        "payload": {"prompt_hash": "deadbeef", "raw_retained": False},
        "raw_prompt_retained": False,
        "raw_tool_output_retained": False,
    }
    write_event(envelope, root=spool_root)
    result = ingest(root=spool_root, db_path=db_path)

    assert result.processed == 1
    assert result.failed == 0

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT event_id, event_type, raw_prompt_retained FROM canonical_events WHERE event_id = ?",
        ("int-test-001",),
    ).fetchone()
    conn.close()

    assert row is not None
    assert row[0] == "int-test-001"
    assert row[1] == "prompt.lifecycle.submitted"
    assert row[2] == 0


def test_no_raw_prompt_in_sqlite(spool_root):
    """Assert canonical_events row has raw_prompt_retained = 0."""
    from emitters.claude_code.emitter import normalize_user_prompt_submit
    from emitters.shared.spool_writer import write_envelopes

    db_path = spool_root / "studio.db"
    envelopes = normalize_user_prompt_submit({"prompt": "secret prompt text"}, root=spool_root)

    # Write to spool and use ingest directly with explicit db_path
    from spool.writer import write_event
    from spool.ingestor import ingest

    for env in envelopes:
        write_event(env.to_dict(), root=spool_root)
    ingest(root=spool_root, db_path=db_path)

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("SELECT payload, raw_prompt_retained FROM canonical_events").fetchall()
    conn.close()

    assert len(rows) >= 1
    for payload_json, raw_retained in rows:
        assert raw_retained == 0
        payload = json.loads(payload_json)
        assert "secret prompt text" not in json.dumps(payload)
