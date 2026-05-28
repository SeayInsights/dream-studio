"""Verify the DREAM_STUDIO_DB_PATH env-var override is honored at every
delegated call site introduced by the PR-1 isolation fix.

The crash that motivated this work (`test_spool_end_to_end.py` second test
silently killing pytest on Windows) was caused by the emitter and ingestor
bypassing the canonical `core.config.database._default_db_path()` and
hardcoding the real operator DB path. These tests are the regression guard
that pins the delegation in place.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def test_emitter_get_db_path_honors_env_override(monkeypatch, tmp_path: Path) -> None:
    """`emitters.claude_code.project._get_db_path` returns the env-overridden path."""
    target = tmp_path / "redirected.db"
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(target))

    from emitters.claude_code.project import _get_db_path

    assert _get_db_path() == target


def test_ingest_writes_to_env_override_db(monkeypatch, tmp_path: Path) -> None:
    """`spool.ingestor.ingest` with no db_path arg writes to the env-overridden DB."""
    spool_root = tmp_path / "spool-root"
    spool_root.mkdir()
    target_db = tmp_path / "ingested.db"
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(target_db))

    from canonical.events.envelope import CanonicalEventEnvelope
    from canonical.events.types import EventType
    from emitters.shared.spool_writer import write_envelopes
    from spool.ingestor import ingest

    envelope = CanonicalEventEnvelope(
        event_type=EventType.WORK_ORDER_STARTED.value,
        session_id=None,
        payload={
            "work_order_id": "test-wo",
            "project_id": "test-proj",
            "title": "Test WO",
            "type": "api_endpoint",
        },
    )
    write_envelopes([envelope], root=spool_root)

    result = ingest(root=spool_root)

    assert result.processed == 1
    assert target_db.is_file(), "ingest() did not write to the env-overridden DB"
    conn = sqlite3.connect(str(target_db))
    try:
        rows = conn.execute("SELECT event_id FROM canonical_events").fetchall()
    finally:
        conn.close()
    assert len(rows) == 1
    assert rows[0][0] == envelope.event_id
