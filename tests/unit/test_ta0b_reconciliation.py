"""TA0b — Dual Event Store Reconciliation tests.

Covers:
  - Ingestor domain-validation warnings
  - execution_events_projection apply() correctness, idempotency, and type-filtering
  - Integration: spool → ingest → execution_events row
  - Direct-written rows have NULL _built_from_event_id
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Test 1: domain validation warning in ingestor (unit)
# ---------------------------------------------------------------------------


def test_ingestor_warns_on_missing_domain(tmp_path, capsys):
    """Ingestor prints a stderr warning for unregistered event types."""
    from spool.ingestor import ingest

    # The spool root is tmp_path / ".dream-studio" / "events" — that is the
    # directory that contains spool/, processing/, processed/, failed/ subdirs.
    spool_root = tmp_path / ".dream-studio" / "events"
    spool_dir = spool_root / "spool"
    spool_dir.mkdir(parents=True)

    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "test.unregistered.event.type",
        "timestamp": "2026-05-21T00:00:00+00:00",
        "schema_version": 1,
        "trace": {},
        "payload": {},
    }
    (spool_dir / f"{event['event_id']}.json").write_text(json.dumps(event), encoding="utf-8")

    db_path = tmp_path / "test.db"
    ingest(root=spool_root, db_path=db_path)

    captured = capsys.readouterr()
    assert "not in registry" in captured.err
    assert event["event_id"] in captured.err


# ---------------------------------------------------------------------------
# Test 2: no warning when domain is present (unit)
# ---------------------------------------------------------------------------


def test_ingestor_no_warning_when_domain_present(tmp_path, capsys):
    """Ingestor does NOT print a domain warning when trace.domain is set."""
    from spool.ingestor import ingest

    spool_root = tmp_path / ".dream-studio" / "events"
    spool_dir = spool_root / "spool"
    spool_dir.mkdir(parents=True)

    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "tool.execution.completed",
        "timestamp": "2026-05-21T00:00:00+00:00",
        "schema_version": 1,
        "trace": {"domain": "telemetry"},
        "payload": {},
    }
    (spool_dir / f"{event['event_id']}.json").write_text(json.dumps(event), encoding="utf-8")

    db_path = tmp_path / "test.db"
    ingest(root=spool_root, db_path=db_path)

    captured = capsys.readouterr()
    assert "missing trace.domain" not in captured.err


# ---------------------------------------------------------------------------
# Test 3: execution_events projection writes correct row (unit)
# ---------------------------------------------------------------------------


def test_projection_writes_execution_event(tmp_path):
    """Projection creates an execution_events row from a canonical event."""
    from projections.core.execution_events_projection import apply

    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("""CREATE TABLE execution_events (
        event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL,
        event_name TEXT NOT NULL, project_id TEXT, milestone_id TEXT,
        task_id TEXT, process_run_id TEXT, parent_event_id TEXT,
        actor_type TEXT, actor_id TEXT, agent_id TEXT, skill_id TEXT,
        workflow_id TEXT, hook_id TEXT, tool_id TEXT, model_id TEXT,
        adapter_id TEXT, source_refs_json TEXT NOT NULL DEFAULT '[]',
        evidence_refs_json TEXT NOT NULL DEFAULT '[]',
        metadata_json TEXT NOT NULL DEFAULT '{}', outcome_status TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        _built_from_event_id TEXT
    )""")

    event_id = str(uuid.uuid4())
    event_data = {
        "event_id": event_id,
        "event_type": "execution.completed",
        "timestamp": "2026-05-21T00:00:00+00:00",
        "schema_version": 1,
        "trace": {"domain": "telemetry", "project_id": "proj-1", "task_id": "task-1"},
        "payload": {"event_name": "test run", "outcome_status": "success"},
    }

    result = apply(event_data, conn)
    assert result is True

    row = conn.execute(
        "SELECT event_type, event_name, project_id, task_id, outcome_status, _built_from_event_id"
        " FROM execution_events WHERE _built_from_event_id = ?",
        (event_id,),
    ).fetchone()
    assert row is not None
    assert row[0] == "execution.completed"
    assert row[1] == "test run"
    assert row[2] == "proj-1"
    assert row[3] == "task-1"
    assert row[4] == "success"
    assert row[5] == event_id

    conn.close()


# ---------------------------------------------------------------------------
# Test 4: projection is idempotent (unit)
# ---------------------------------------------------------------------------


def test_projection_is_idempotent(tmp_path):
    """Calling apply() twice with the same event produces exactly one row."""
    from projections.core.execution_events_projection import apply

    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("""CREATE TABLE execution_events (
        event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL,
        event_name TEXT NOT NULL, project_id TEXT, milestone_id TEXT,
        task_id TEXT, process_run_id TEXT, parent_event_id TEXT,
        actor_type TEXT, actor_id TEXT, agent_id TEXT, skill_id TEXT,
        workflow_id TEXT, hook_id TEXT, tool_id TEXT, model_id TEXT,
        adapter_id TEXT, source_refs_json TEXT NOT NULL DEFAULT '[]',
        evidence_refs_json TEXT NOT NULL DEFAULT '[]',
        metadata_json TEXT NOT NULL DEFAULT '{}', outcome_status TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        _built_from_event_id TEXT
    )""")

    event_id = str(uuid.uuid4())
    event_data = {
        "event_id": event_id,
        "event_type": "execution.completed",
        "timestamp": "2026-05-21T00:00:00+00:00",
        "schema_version": 1,
        "trace": {"domain": "telemetry", "project_id": "proj-2"},
        "payload": {"event_name": "idempotent test"},
    }

    first = apply(event_data, conn)
    assert first is True

    second = apply(event_data, conn)
    assert second is False

    count = conn.execute("SELECT COUNT(*) FROM execution_events").fetchone()[0]
    assert count == 1

    conn.close()


# ---------------------------------------------------------------------------
# Test 5: non-execution events are not projected (unit)
# ---------------------------------------------------------------------------


def test_projection_skips_non_execution_events(tmp_path):
    """apply() returns False and writes nothing for non-execution event types."""
    from projections.core.execution_events_projection import apply

    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("""CREATE TABLE execution_events (
        event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL,
        event_name TEXT NOT NULL, project_id TEXT, milestone_id TEXT,
        task_id TEXT, process_run_id TEXT, parent_event_id TEXT,
        actor_type TEXT, actor_id TEXT, agent_id TEXT, skill_id TEXT,
        workflow_id TEXT, hook_id TEXT, tool_id TEXT, model_id TEXT,
        adapter_id TEXT, source_refs_json TEXT NOT NULL DEFAULT '[]',
        evidence_refs_json TEXT NOT NULL DEFAULT '[]',
        metadata_json TEXT NOT NULL DEFAULT '{}', outcome_status TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        _built_from_event_id TEXT
    )""")

    event_data = {
        "event_id": str(uuid.uuid4()),
        "event_type": "skill.invoked",
        "timestamp": "2026-05-21T00:00:00+00:00",
        "schema_version": 1,
        "trace": {"domain": "telemetry"},
        "payload": {},
    }

    result = apply(event_data, conn)
    assert result is False

    count = conn.execute("SELECT COUNT(*) FROM execution_events").fetchone()[0]
    assert count == 0

    conn.close()


# ---------------------------------------------------------------------------
# Test 6: integration — canonical pipeline produces execution_events row
# ---------------------------------------------------------------------------


def test_canonical_pipeline_produces_execution_events_row(tmp_path):
    """End-to-end: spool event → ingest → execution_events via projection."""
    from spool.ingestor import ingest
    from core.config.sqlite_bootstrap import bootstrap_database

    spool_root = tmp_path / ".dream-studio" / "events"
    spool_dir = spool_root / "spool"
    spool_dir.mkdir(parents=True)

    event_id = str(uuid.uuid4())
    event = {
        "event_id": event_id,
        "event_type": "execution.started",
        "timestamp": "2026-05-21T00:00:00+00:00",
        "schema_version": 1,
        "trace": {"domain": "telemetry", "project_id": "proj-x"},
        "payload": {"event_name": "integration test run"},
    }
    (spool_dir / f"{event_id}.json").write_text(json.dumps(event), encoding="utf-8")

    db_path = tmp_path / "test.db"

    # Bootstrap all migrations (037 creates execution_events, 059 adds _built_from_event_id)
    # so the projection can write into execution_events when the ingestor runs.
    bootstrap_database(db_path)

    result = ingest(root=spool_root, db_path=db_path)
    assert result.processed == 1

    conn = sqlite3.connect(str(db_path))
    # Canonical event should be present
    row = conn.execute(
        "SELECT event_id FROM canonical_events WHERE event_id = ?", (event_id,)
    ).fetchone()
    assert row is not None

    # Projection should have created an execution_events row
    proj_row = conn.execute(
        "SELECT _built_from_event_id FROM execution_events WHERE _built_from_event_id = ?",
        (event_id,),
    ).fetchone()
    assert proj_row is not None, "execution_events projection row not found"

    conn.close()


# ---------------------------------------------------------------------------
# Test 7: direct-written rows have NULL _built_from_event_id
# ---------------------------------------------------------------------------


def test_direct_written_rows_have_null_link(tmp_path):
    """Historical direct-written execution_events rows have _built_from_event_id = NULL."""
    from core.config.sqlite_bootstrap import bootstrap_database

    db_path = tmp_path / "test.db"
    bootstrap_database(db_path)  # applies all migrations including 059

    conn = sqlite3.connect(str(db_path))
    # Insert a row the old way (simulating historical data)
    conn.execute(
        """INSERT INTO execution_events
           (event_id, event_type, event_name, source_refs_json, evidence_refs_json, metadata_json)
           VALUES (?, 'execution.complete', 'legacy', '[]', '[]', '{}')""",
        (str(uuid.uuid4()),),
    )
    conn.commit()

    row = conn.execute(
        "SELECT _built_from_event_id FROM execution_events WHERE event_type = 'execution.complete'"
    ).fetchone()
    assert row is not None
    assert row[0] is None  # no canonical link for direct-written rows

    conn.close()
