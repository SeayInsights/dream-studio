"""TA1: Task lifecycle event tests.

Covers task.created, task.completed (enriched trace), and task.deleted.
task.started has no call site in this codebase (tasks go pending → complete
with no in_progress state); that type is registered but unimplemented — noted
in the TA1 PR.

The migration-064 backfill test section (WO-SQUASH-BASELINE, 5fd84891,
2026-07-04: 064_backfill_task_creation_events.sql was a one-time, data-only
backfill migration with no persistent DDL, collapsed into
142_lean_baseline.sql, which does not replay backfill INSERT...SELECT logic
against historical rows) was removed -- there is no current file or schema
object left for those tests to target.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

# ── fixtures ──────────────────────────────────────────────────────────────────

PROJECT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
MILESTONE_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
WO_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
TASK_A = "11111111-1111-1111-1111-111111111111"
TASK_B = "22222222-2222-2222-2222-222222222222"
NOW = "2026-05-21T00:00:00+00:00"


@pytest.fixture
def db_home(tmp_path):
    db_path = tmp_path / "state" / "studio.db"
    db_path.parent.mkdir(parents=True)
    bootstrap_database(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO business_projects (project_id, name, description, status, created_at, updated_at)"
            " VALUES (?, 'Test Project', 'desc', 'active', ?, ?)",
            (PROJECT_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_milestones"
            " (milestone_id, project_id, title, status, created_at, updated_at)"
            " VALUES (?, ?, 'M1', 'active', ?, ?)",
            (MILESTONE_ID, PROJECT_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, ?, 'WO1', NULL, 'in_progress', 'documentation', ?, ?)",
            (WO_ID, PROJECT_ID, MILESTONE_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, description, status,"
            " created_at, updated_at)"
            " VALUES (?, ?, ?, 'Task A', 'desc A', 'pending', ?, ?)",
            (TASK_A, WO_ID, PROJECT_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, description, status,"
            " created_at, updated_at)"
            " VALUES (?, ?, ?, 'Task B', 'desc B', 'pending', ?, ?)",
            (TASK_B, WO_ID, PROJECT_ID, NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return tmp_path


def _spool_events(spool_root: Path) -> list[dict]:
    # sync_tick() moves files from spool/ → processed/ (or failed/) after ingestion;
    # check all three directories so tests pass whether or not sync_tick ran.
    events = []
    for subdir in ("spool", "processed", "failed"):
        d = spool_root / subdir
        if d.exists():
            events.extend(
                json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))
            )
    return events


def _events_of_type(spool_root: Path, event_type: str) -> list[dict]:
    return [e for e in _spool_events(spool_root) if e.get("event_type") == event_type]


# ── task.created from create_task() ──────────────────────────────────────────


def test_create_task_emits_task_created_event(db_home, tmp_path, monkeypatch):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    from core.work_orders.mutations import create_task

    result = create_task(
        work_order_id=WO_ID,
        project_id=PROJECT_ID,
        title="New Task",
        description="some work",
        source_root=tmp_path,
        dream_studio_home=db_home,
    )
    assert result["ok"] is True
    task_id = result["task_id"]

    events = _events_of_type(tmp_path / "spool-root", "task.created")
    assert len(events) == 1
    ev = events[0]
    assert ev["trace"]["domain"] == "sdlc"
    assert ev["trace"]["project_id"] == PROJECT_ID
    assert ev["trace"]["milestone_id"] == MILESTONE_ID
    assert ev["trace"]["work_order_id"] == WO_ID
    assert ev["trace"]["task_id"] == task_id
    assert ev["trace"]["attribution_status"] == "fully_attributed"
    assert ev["payload"]["title"] == "New Task"
    assert ev["payload"]["status"] == "created"


def test_create_task_event_uses_canonical_envelope_schema(db_home, tmp_path, monkeypatch):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    from canonical.events.envelope import validate_envelope
    from core.work_orders.mutations import create_task

    create_task(
        work_order_id=WO_ID,
        project_id=PROJECT_ID,
        title="Envelope Test",
        source_root=tmp_path,
        dream_studio_home=db_home,
    )
    events = _events_of_type(tmp_path / "spool-root", "task.created")
    assert len(events) == 1
    errors = validate_envelope(events[0])
    assert errors == [], f"Envelope validation errors: {errors}"


# ── task.completed trace enrichment ──────────────────────────────────────────


def test_task_completed_trace_includes_milestone_and_project(db_home, tmp_path, monkeypatch):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    from core.work_orders.mutations import mark_task_done

    result = mark_task_done(
        work_order_id=WO_ID,
        task_id=TASK_A,
        source_root=tmp_path,
        dream_studio_home=db_home,
    )
    assert result["ok"] is True

    events = _events_of_type(tmp_path / "spool-root", "task.completed")
    assert len(events) == 1
    ev = events[0]
    assert ev["trace"]["project_id"] == PROJECT_ID
    assert ev["trace"]["milestone_id"] == MILESTONE_ID
    assert ev["trace"]["work_order_id"] == WO_ID
    assert ev["trace"]["task_id"] == TASK_A
    assert ev["trace"]["attribution_status"] == "fully_attributed"


# ── task.deleted on cascade project delete ───────────────────────────────────


def test_delete_project_emits_task_deleted_per_task(db_home, tmp_path, monkeypatch):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    from core.projects.mutations import delete_project

    result = delete_project(
        project_id=PROJECT_ID,
        confirm=True,
        source_root=tmp_path,
        dream_studio_home=db_home,
    )
    assert result["ok"] is True

    events = _events_of_type(tmp_path / "spool-root", "task.deleted")
    assert len(events) == 2, f"Expected 2 task.deleted events, got {len(events)}"
    task_ids_in_events = {e["trace"]["task_id"] for e in events}
    assert task_ids_in_events == {TASK_A, TASK_B}

    for ev in events:
        assert ev["trace"]["domain"] == "sdlc"
        assert ev["trace"]["project_id"] == PROJECT_ID
        assert ev["trace"]["milestone_id"] == MILESTONE_ID
        assert ev["trace"]["work_order_id"] == WO_ID
        assert ev["trace"]["attribution_status"] == "fully_attributed"
        assert ev["payload"]["deletion_context"] == "cascaded_from_project_delete"


def test_delete_project_also_emits_project_deleted(db_home, tmp_path, monkeypatch):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    from core.projects.mutations import delete_project

    delete_project(
        project_id=PROJECT_ID,
        confirm=True,
        source_root=tmp_path,
        dream_studio_home=db_home,
    )
    project_events = _events_of_type(tmp_path / "spool-root", "project.deleted")
    assert len(project_events) == 1


# ── backfill migration ────────────────────────────────────────────────────────
#
# Section removed (WO-SQUASH-BASELINE, 5fd84891, 2026-07-04): see module
# docstring. The removed tests exercised 064_backfill_task_creation_events.sql
# against a hand-built pre-070 "legacy" DB (ds_tasks/ds_work_orders, both
# tombstoned — see tests/unit/schema_tombstones_data.py).


# ── integration: create_task → DB + spool ────────────────────────────────────


def test_create_task_integration_emits_event(db_home, tmp_path, monkeypatch):
    # Phase 18.2.3: create_task() is event-sourced. It emits task.created to the
    # spool; TaskProjection applies it to business_tasks asynchronously. The DB
    # row is NOT written synchronously by this function any longer.
    spool_root = tmp_path / "spool-root"
    monkeypatch.setenv("DS_SPOOL_ROOT", str(spool_root))
    from core.work_orders.mutations import create_task

    result = create_task(
        work_order_id=WO_ID,
        project_id=PROJECT_ID,
        title="Integration Task",
        source_root=tmp_path,
        dream_studio_home=db_home,
    )
    assert result["ok"] is True
    assert result["task_id"] is not None
    assert result["title"] == "Integration Task"

    spool_files = list(spool_root.rglob("*.jsonl")) + list(spool_root.rglob("*.json"))
    events = []
    for f in spool_files:
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    import json as _json

                    events.append(_json.loads(line))
                except Exception:
                    pass
    created = [e for e in events if e.get("event_type") == "task.created"]
    assert created, "Expected task.created event in spool"
    assert created[0]["trace"]["task_id"] == result["task_id"]


def test_complete_task_integration_event_has_full_trace(db_home, tmp_path, monkeypatch):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    from core.work_orders.mutations import mark_task_done

    result = mark_task_done(
        work_order_id=WO_ID,
        task_id=TASK_B,
        source_root=tmp_path,
        dream_studio_home=db_home,
    )
    assert result["ok"] is True

    events = _events_of_type(tmp_path / "spool-root", "task.completed")
    assert len(events) == 1
    trace = events[0]["trace"]
    assert trace["project_id"] == PROJECT_ID
    assert trace["milestone_id"] == MILESTONE_ID
    assert trace["work_order_id"] == WO_ID
    assert trace["task_id"] == TASK_B
