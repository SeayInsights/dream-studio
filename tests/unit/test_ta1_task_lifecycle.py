"""TA1: Task lifecycle event tests.

Covers task.created, task.completed (enriched trace), task.deleted, and the
064 backfill migration.  task.started has no call site in this codebase (tasks
go pending → complete with no in_progress state); that type is registered but
unimplemented — noted in the TA1 PR.
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
    spool_dir = spool_root / "spool"
    if not spool_dir.exists():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(spool_dir.glob("*.json"))]


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

# Migration 064 reads from ds_tasks/ds_work_orders, which are dropped by
# migration 070.  These tests use a separate minimal "legacy" DB with the
# pre-070 schema so migration 064 can be exercised correctly in isolation.

_CANONICAL_EVENTS_DDL = """
    CREATE TABLE IF NOT EXISTS canonical_events (
        event_id TEXT PRIMARY KEY,
        event_type TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        trace JSON NOT NULL DEFAULT '{}',
        severity TEXT NOT NULL DEFAULT 'info',
        payload JSON NOT NULL DEFAULT '{}',
        raw_prompt_retained INTEGER NOT NULL DEFAULT 0,
        raw_tool_output_retained INTEGER NOT NULL DEFAULT 0,
        schema_version INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
"""


@pytest.fixture
def legacy_db_path(tmp_path):
    """Minimal pre-070 DB for migration-064 backfill tests."""
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(f"""
            {_CANONICAL_EVENTS_DDL};
            CREATE TABLE ds_work_orders (
                work_order_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                milestone_id TEXT,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                work_order_type TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE ds_tasks (
                task_id TEXT PRIMARY KEY,
                work_order_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        conn.execute(
            "INSERT INTO ds_work_orders"
            " (work_order_id, project_id, milestone_id, title, status, created_at, updated_at)"
            " VALUES (?, ?, ?, 'WO1', 'open', ?, ?)",
            (WO_ID, PROJECT_ID, MILESTONE_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO ds_tasks"
            " (task_id, work_order_id, project_id, title, description, status, created_at, updated_at)"
            " VALUES (?, ?, ?, 'Task A', 'desc A', 'pending', ?, ?)",
            (TASK_A, WO_ID, PROJECT_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO ds_tasks"
            " (task_id, work_order_id, project_id, title, description, status, created_at, updated_at)"
            " VALUES (?, ?, ?, 'Task B', 'desc B', 'pending', ?, ?)",
            (TASK_B, WO_ID, PROJECT_ID, NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def _run_migration_064(db_path: Path) -> None:
    sql_path = (
        Path(__file__).resolve().parents[2]
        / "core"
        / "event_store"
        / "migrations"
        / "064_backfill_task_creation_events.sql"
    )
    sql = sql_path.read_text(encoding="utf-8")
    conn = sqlite3.connect(str(db_path))
    try:
        # canonical_events is created by the ingestor at runtime, not via migrations.
        conn.execute(_CANONICAL_EVENTS_DDL)
        conn.commit()
        conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()


def test_backfill_migration_produces_event_per_task(legacy_db_path):
    _run_migration_064(legacy_db_path)
    conn = sqlite3.connect(str(legacy_db_path))
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM canonical_events WHERE event_type = 'task.created'",
        ).fetchone()[0]
    finally:
        conn.close()
    assert count == 2


def test_backfill_migration_is_idempotent(legacy_db_path):
    _run_migration_064(legacy_db_path)
    _run_migration_064(legacy_db_path)
    conn = sqlite3.connect(str(legacy_db_path))
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM canonical_events WHERE event_type = 'task.created'",
        ).fetchone()[0]
    finally:
        conn.close()
    assert count == 2


def test_backfill_migration_sets_attribution_status_backfill(legacy_db_path):
    _run_migration_064(legacy_db_path)
    conn = sqlite3.connect(str(legacy_db_path))
    try:
        rows = conn.execute(
            "SELECT trace FROM canonical_events WHERE event_type = 'task.created'",
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 2
    for (trace_json,) in rows:
        trace = json.loads(trace_json)
        assert trace["attribution_status"] == "backfill"


def test_backfill_migration_resolves_full_sdlc_trace(legacy_db_path):
    _run_migration_064(legacy_db_path)
    conn = sqlite3.connect(str(legacy_db_path))
    try:
        rows = conn.execute(
            "SELECT event_id, trace FROM canonical_events WHERE event_type = 'task.created'"
            " ORDER BY event_id",
        ).fetchall()
    finally:
        conn.close()
    traces = {event_id: json.loads(trace_json) for event_id, trace_json in rows}
    for event_id, trace in traces.items():
        assert trace["domain"] == "sdlc"
        assert trace["project_id"] == PROJECT_ID
        assert trace["milestone_id"] == MILESTONE_ID
        assert trace["work_order_id"] == WO_ID
        assert "task_id" in trace


def test_backfill_event_ids_are_deterministic(legacy_db_path):
    _run_migration_064(legacy_db_path)
    conn = sqlite3.connect(str(legacy_db_path))
    try:
        event_ids = [
            row[0]
            for row in conn.execute(
                "SELECT event_id FROM canonical_events WHERE event_type = 'task.created'"
                " ORDER BY event_id",
            ).fetchall()
        ]
    finally:
        conn.close()
    assert event_ids == sorted(
        [f"backfill-task-created-{TASK_A}", f"backfill-task-created-{TASK_B}"]
    )


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
