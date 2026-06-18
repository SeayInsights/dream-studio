"""Integration tests for WO-ATTRIBUTION-NORMALIZE: project attribution pipeline.

T2 — new execution_events carry resolved UUIDs (capture fix).
T3 — dream_studio_activity_non_empty: activity route returns events post-backfill.
T4 (placeholder T5) — end-to-end: resolver + capture + backfill + read.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.config.database import DB_PATH_ENV, DatabaseRuntime
from core.config.sqlite_bootstrap import bootstrap_database

# ── Shared helpers ────────────────────────────────────────────────────────────

DS_UUID = "29ff0914-b15a-4a84-8bc7-5619cc5240f6"


def _make_db(tmp_path: Path, name: str) -> Path:
    """Bootstrap a full-schema test DB with a seeded dream-studio project."""
    db_path = tmp_path / name
    bootstrap_database(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # Seed the canonical project row
        conn.execute(
            "INSERT OR IGNORE INTO business_projects"
            " (project_id, name, project_path, status, created_at, updated_at)"
            " VALUES (?, ?, ?, 'active', datetime('now'), datetime('now'))",
            (DS_UUID, "dream-studio", "/builds/dream-studio-clean"),
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def _client(db_path: Path, monkeypatch) -> TestClient:
    from projections.api.main import app

    DatabaseRuntime.reset_instance()
    monkeypatch.setenv(DB_PATH_ENV, str(db_path))
    return TestClient(app)


# ── T2: test_new_events_attribute_to_registered_uuid ─────────────────────────


def test_new_events_attribute_to_registered_uuid(tmp_path: Path) -> None:
    """T2: record_execution_event resolves project key to UUID at write time.

    Seeds a business_projects row, then calls record_execution_event with
    'dream-studio' as project_id (the free-text key). Verifies the stored
    row holds the UUID, not the raw key.
    """
    from core.telemetry.execution_spine import record_execution_event

    db_path = _make_db(tmp_path, "capture-test.db")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        event_id = "evt-capture-" + uuid.uuid4().hex[:8]
        record_execution_event(
            conn,
            event_id=event_id,
            event_type="skill.invoked",
            event_name="capture test event",
            project_id="dream-studio",  # free-text key — should be resolved
            outcome_status="completed",
        )
        conn.commit()

        row = conn.execute(
            "SELECT project_id FROM execution_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        assert row is not None, "Event was not written"
        assert row["project_id"] == DS_UUID, (
            f"Expected UUID {DS_UUID!r}, got {row['project_id']!r}. "
            "Capture fix not working: project key was not resolved at write time."
        )
    finally:
        conn.close()


# ── T3: test_dream_studio_activity_non_empty ──────────────────────────────────


def test_dream_studio_activity_non_empty(tmp_path: Path, monkeypatch) -> None:
    """T3: /api/v1/projects/{uuid}/activity returns non-empty activity list.

    Inserts execution_events with DS_UUID as project_id (as backfill would
    produce) and verifies the activity endpoint returns non-empty results.
    """
    db_path = _make_db(tmp_path, "activity-test.db")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # Insert events directly with the UUID (simulating post-backfill state)
        for i in range(3):
            conn.execute(
                "INSERT INTO execution_events"
                " (event_id, event_type, event_name, project_id, outcome_status)"
                " VALUES (?, 'skill.invoked', 'activity test', ?, 'completed')",
                (f"evt-activity-{i}", DS_UUID),
            )
        conn.commit()
    finally:
        conn.close()

    client = _client(db_path, monkeypatch)
    resp = client.get(f"/api/v1/projects/{DS_UUID}/activity")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "activities" in data, f"Missing 'activities' key: {data}"
    assert data["count"] > 0, (
        f"Activity count is 0 after inserting UUID-attributed events. " f"Response: {data}"
    )
    assert len(data["activities"]) > 0, "activities list is empty"


# ── T4: test_end_to_end ───────────────────────────────────────────────────────


def test_end_to_end(tmp_path: Path, monkeypatch) -> None:
    """T4/T5 (end-to-end): resolver -> capture -> backfill -> read query all produce UUID.

    1. Capture: record_execution_event with free-text key -> stored as UUID
    2. Backfill: old free-text key rows -> remapped to UUID
    3. Read: /api/v1/projects/{uuid}/activity returns events from both paths
    """
    from core.projects.attribution import backfill_execution_events
    from core.telemetry.execution_spine import record_execution_event

    db_path = _make_db(tmp_path, "e2e-test.db")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # 1. Capture path: new event with free-text key
        event_id_new = "evt-e2e-new-" + uuid.uuid4().hex[:8]
        record_execution_event(
            conn,
            event_id=event_id_new,
            event_type="skill.invoked",
            event_name="e2e capture test",
            project_id="dream-studio",
            outcome_status="completed",
        )

        # 2. Backfill path: inject an old-style free-text row
        old_event_id = "evt-e2e-old-" + uuid.uuid4().hex[:8]
        conn.execute(
            "INSERT OR IGNORE INTO execution_events"
            " (event_id, event_type, event_name, project_id, outcome_status)"
            " VALUES (?, 'skill.invoked', 'legacy event', 'dream-studio-clean', 'completed')",
            (old_event_id,),
        )
        conn.commit()

        backfill_summary = backfill_execution_events(conn)
        conn.commit()

        # Both keys should resolve to DS_UUID
        assert (
            "dream-studio-clean" in backfill_summary
        ), "'dream-studio-clean' was not remapped by backfill"

        # 3. Verify both events now carry the UUID
        count = conn.execute(
            "SELECT COUNT(*) FROM execution_events WHERE project_id = ?",
            (DS_UUID,),
        ).fetchone()[0]
        assert count >= 2, (
            f"Expected at least 2 events with UUID, got {count}. "
            "Both capture and backfill paths must produce UUID-attributed rows."
        )
    finally:
        conn.close()

    # 4. Read query via API
    client = _client(db_path, monkeypatch)
    resp = client.get(f"/api/v1/projects/{DS_UUID}/activity")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert (
        data["count"] >= 2
    ), f"API activity count {data['count']} is too low; expected >= 2. Response: {data}"
