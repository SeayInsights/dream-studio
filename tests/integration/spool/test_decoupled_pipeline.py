from __future__ import annotations
import json
import sqlite3
import pytest
from pathlib import Path


def test_write_does_not_ingest(spool_root):
    """write_envelopes writes to spool/ only — SQLite is untouched."""
    from canonical.events.envelope import CanonicalEventEnvelope
    from emitters.shared.spool_writer import write_envelopes
    from spool.states import SpoolState, state_dir

    db = spool_root / "test.db"
    envelope = CanonicalEventEnvelope(
        event_type="test.production.event",
        session_id=None,
        payload={"key": "value"},
        confidence="unavailable",
        project_id=None,
    )
    write_envelopes([envelope], root=spool_root)

    # Spool file exists
    spool_dir = state_dir(SpoolState.SPOOL, spool_root)
    spool_files = list(spool_dir.glob("*.json"))
    assert len(spool_files) == 1

    # SQLite does NOT have the event yet
    if db.exists():
        conn = sqlite3.connect(str(db))
        rows = conn.execute("SELECT * FROM canonical_events WHERE event_id = ?", (envelope.event_id,)).fetchall()
        conn.close()
        assert rows == []


def test_ingest_pending_lands_in_sqlite(spool_root):
    """After ingest_pending, the event is in canonical_events."""
    from canonical.events.envelope import CanonicalEventEnvelope
    from emitters.shared.spool_writer import write_envelopes
    from spool.ingestor import ingest_pending
    import sqlite3

    db = spool_root / "test.db"
    envelope = CanonicalEventEnvelope(
        event_type="test.production.event",
        session_id=None,
        payload={"key": "value"},
        confidence="unavailable",
        project_id=None,
    )
    write_envelopes([envelope], root=spool_root)
    result = ingest_pending(root=spool_root, db_path=db)

    assert result.processed == 1
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT event_id, event_type FROM canonical_events WHERE event_id = ?",
        (envelope.event_id,)
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0][1] == "test.production.event"
