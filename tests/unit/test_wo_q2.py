"""WO-Q2 — Guarantee creation materialization.

Tests the emit-then-tick Pattern C guarantee: SDLC creators
(register_project / create_milestone / create_work_order / create_task)
must produce rows that are queryable on return without daemon dependency.

Coverage:
  1. ProjectionRunner.tick() exists and runs a single cycle
  2. sync_tick() module-level helper is importable and non-raising
  3. create_milestone + sync_tick materialises business_milestones row
  4. create_work_order + sync_tick materialises business_work_orders row
  5. create_task reads milestone_id from already-materialised WO (Pattern C guarantee)
  6. Full E2E chain: project → milestone → WO → task all queryable on return
  7. check_sdlc_consistency() detects stranded creation events
"""

from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ---------------------------------------------------------------------------
# DDL — mirrors the live schema for all SDLC read-model tables
# ---------------------------------------------------------------------------

_BUSINESS_PROJECTS_DDL = """
CREATE TABLE IF NOT EXISTS business_projects (
    project_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    project_path TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

_BUSINESS_MILESTONES_DDL = """
CREATE TABLE IF NOT EXISTS business_milestones (
    milestone_id TEXT PRIMARY KEY,
    project_id TEXT,
    title TEXT NOT NULL DEFAULT '(pending)',
    description TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    order_index INTEGER DEFAULT 0,
    due_date TEXT,
    stage_gate_json TEXT,
    validation_expectations_json TEXT,
    security_readiness_checks_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    source_event_id TEXT,
    last_event_id TEXT
);
"""

_BUSINESS_WORK_ORDERS_DDL = """
CREATE TABLE IF NOT EXISTS business_work_orders (
    work_order_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    title TEXT,
    status TEXT NOT NULL DEFAULT 'created',
    description TEXT,
    work_order_type TEXT,
    created_at TEXT,
    started_at TEXT,
    closed_at TEXT,
    blocked_at TEXT,
    unblocked_at TEXT,
    block_reason TEXT,
    source_event_id TEXT,
    last_event_id TEXT,
    last_updated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    updated_at TEXT
);
"""

_BUSINESS_TASKS_DDL = """
CREATE TABLE IF NOT EXISTS business_tasks (
    task_id TEXT PRIMARY KEY,
    work_order_id TEXT,
    project_id TEXT,
    title TEXT NOT NULL DEFAULT '(pending)',
    description TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    source_event_id TEXT,
    last_event_id TEXT
);
"""

_BUSINESS_CANONICAL_DDL = """
CREATE TABLE IF NOT EXISTS business_canonical_events (
    event_id TEXT PRIMARY KEY,
    received_at TEXT NOT NULL DEFAULT (datetime('now','utc')),
    event_type TEXT NOT NULL,
    event_timestamp TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    trace JSON NOT NULL DEFAULT '{}',
    payload JSON NOT NULL DEFAULT '{}',
    correlation_id TEXT,
    project_id TEXT,
    milestone_id TEXT,
    work_order_id TEXT,
    task_id TEXT,
    severity TEXT NOT NULL DEFAULT 'info',
    source TEXT NOT NULL DEFAULT 'ingestor'
);
"""

_AI_CANONICAL_DDL = """
CREATE TABLE IF NOT EXISTS ai_canonical_events (
    event_id TEXT PRIMARY KEY,
    received_at TEXT NOT NULL DEFAULT (datetime('now','utc')),
    event_type TEXT NOT NULL,
    event_timestamp TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    trace JSON NOT NULL DEFAULT '{}',
    payload JSON NOT NULL DEFAULT '{}',
    correlation_id TEXT,
    session_id TEXT,
    skill_id TEXT,
    workflow_id TEXT,
    agent_id TEXT,
    hook_id TEXT,
    model_id TEXT,
    severity TEXT NOT NULL DEFAULT 'info',
    source TEXT NOT NULL DEFAULT 'ingestor'
);
"""

_PROJECTION_STATE_DDL = """
CREATE TABLE IF NOT EXISTS projection_state (
    projection_name TEXT PRIMARY KEY,
    last_processed_business_event_id TEXT,
    last_processed_ai_event_id TEXT,
    last_run_at TEXT,
    events_processed_total INTEGER NOT NULL DEFAULT 0,
    events_failed_total INTEGER NOT NULL DEFAULT 0
);
"""

_RETRY_QUEUE_DDL = """
CREATE TABLE IF NOT EXISTS projection_retry_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    event_source TEXT NOT NULL,
    projection_name TEXT NOT NULL,
    next_retry_at TEXT NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0
);
"""

_DEAD_LETTER_DDL = """
CREATE TABLE IF NOT EXISTS projection_dead_letter (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    event_source TEXT NOT NULL,
    projection_name TEXT NOT NULL,
    error_message TEXT,
    error_traceback TEXT,
    failed_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_retry_at TEXT,
    status TEXT NOT NULL DEFAULT 'active'
);
"""

_CHECKPOINTS_DDL = """
CREATE TABLE IF NOT EXISTS projection_checkpoints (
    projection_name TEXT PRIMARY KEY,
    last_event_id TEXT NOT NULL DEFAULT '',
    last_timestamp TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z',
    events_processed INTEGER NOT NULL DEFAULT 0,
    last_rebuilt TEXT
);
"""

_ALL_DDL = (
    _BUSINESS_PROJECTS_DDL
    + _BUSINESS_MILESTONES_DDL
    + _BUSINESS_WORK_ORDERS_DDL
    + _BUSINESS_TASKS_DDL
    + _BUSINESS_CANONICAL_DDL
    + _AI_CANONICAL_DDL
    + _PROJECTION_STATE_DDL
    + _RETRY_QUEUE_DDL
    + _DEAD_LETTER_DDL
    + _CHECKPOINTS_DDL
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _reset_db_runtime():
    try:
        from core.config.database import DatabaseRuntime

        DatabaseRuntime.reset_instance()
    except Exception:
        pass


@pytest.fixture
def sdlc_env(tmp_path, monkeypatch):
    """Full SDLC test environment: tmp DB + spool root + monkeypatched resolvers."""
    db_path = tmp_path / "state" / "studio.db"
    db_path.parent.mkdir(parents=True)
    spool_root = tmp_path / "spool_root"

    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_path))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(spool_root))
    _reset_db_runtime()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript("PRAGMA journal_mode = WAL;\n" + _ALL_DDL)
    conn.commit()
    conn.close()

    # Patch _require_db in all SDLC mutation modules so they use the tmp db.
    for module_path in (
        "core.projects.mutations",
        "core.milestones.mutations",
        "core.work_orders.mutations",
    ):
        monkeypatch.setattr(module_path + "._require_db", lambda *a, **kw: db_path)

    yield {"db": db_path, "spool_root": spool_root, "tmp": tmp_path}

    _reset_db_runtime()


def _fetch_row(db_path: Path, table: str, pk_col: str, pk_val: str) -> dict | None:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(f"SELECT * FROM {table} WHERE {pk_col} = ?", (pk_val,)).fetchone()
    conn.close()
    return dict(row) if row else None


def _direct_insert_project(db_path: Path, project_id: str, name: str = "Test Project") -> None:
    """Insert a project directly — mirrors register_project's direct SQL path."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO business_projects (project_id, name, status, created_at, updated_at)"
        " VALUES (?, ?, 'active', ?, ?)",
        (project_id, name, now, now),
    )
    conn.commit()
    conn.close()


def _insert_canonical_event(db_path: Path, event: dict) -> None:
    """Insert directly into business_canonical_events (simulates the ingestor)."""
    import json as _json

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """INSERT OR IGNORE INTO business_canonical_events
           (event_id, event_type, event_timestamp, schema_version,
            trace, payload, project_id, milestone_id, work_order_id, task_id, severity)
           VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, 'info')""",
        (
            event["event_id"],
            event["event_type"],
            event["event_timestamp"],
            _json.dumps(event.get("trace", {})),
            _json.dumps(event.get("payload", {})),
            (event.get("trace") or {}).get("project_id"),
            (event.get("trace") or {}).get("milestone_id"),
            (event.get("trace") or {}).get("work_order_id"),
            (event.get("trace") or {}).get("task_id"),
        ),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# 1. tick() method exists on ProjectionRunner
# ---------------------------------------------------------------------------


def test_projection_runner_tick_method_exists():
    from core.projections.runner import ProjectionRunner

    runner = ProjectionRunner()
    assert callable(getattr(runner, "tick", None)), "ProjectionRunner.tick() must exist"


# ---------------------------------------------------------------------------
# 2. sync_tick() is importable and non-raising with empty spool
# ---------------------------------------------------------------------------


def test_sync_tick_importable_and_non_raising(sdlc_env):
    from core.projections.runner import sync_tick

    # Should not raise even with an empty spool directory
    sync_tick()


# ---------------------------------------------------------------------------
# 3. ProjectionRunner.tick() processes a manually-inserted canonical event
# ---------------------------------------------------------------------------


def test_tick_materialises_milestone_from_canonical_event(sdlc_env):
    from datetime import datetime, timezone

    from core.projections.framework import ProjectionEngine
    from core.projections.milestone_projection import MilestoneProjection

    db_path = sdlc_env["db"]
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    _direct_insert_project(db_path, project_id)

    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "milestone.created",
        "event_timestamp": now,
        "trace": {"project_id": project_id, "milestone_id": milestone_id, "domain": "sdlc"},
        "payload": {"title": "M1 Deliverable", "status": "pending"},
    }
    _insert_canonical_event(db_path, event)

    from core.projections.runner import ProjectionRunner

    runner = ProjectionRunner()
    runner.register(MilestoneProjection())
    runner.tick()

    row = _fetch_row(db_path, "business_milestones", "milestone_id", milestone_id)
    assert row is not None, "milestone row must exist after tick()"
    assert row["title"] == "M1 Deliverable"
    assert row["status"] == "pending"
    assert row["project_id"] == project_id


# ---------------------------------------------------------------------------
# 4. create_milestone + sync_tick → row queryable immediately
# ---------------------------------------------------------------------------


def test_create_milestone_materialises_on_return(sdlc_env):
    from core.milestones.mutations import create_milestone

    db_path = sdlc_env["db"]
    project_id = str(uuid.uuid4())
    _direct_insert_project(db_path, project_id)

    result = create_milestone(
        project_id=project_id,
        title="Delivery Gate",
        description="First milestone",
        source_root=REPO_ROOT,
    )
    assert result["ok"] is True
    milestone_id = result["milestone_id"]

    row = _fetch_row(db_path, "business_milestones", "milestone_id", milestone_id)
    assert (
        row is not None
    ), "business_milestones row must be queryable on return (no daemon dependency)"
    assert row["title"] == "Delivery Gate"


# ---------------------------------------------------------------------------
# 5. create_work_order + sync_tick → row queryable immediately
# ---------------------------------------------------------------------------


def test_create_work_order_materialises_on_return(sdlc_env):
    from core.work_orders.mutations import create_work_order

    db_path = sdlc_env["db"]
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    _direct_insert_project(db_path, project_id)

    result = create_work_order(
        project_id=project_id,
        milestone_id=milestone_id,
        title="WO — Build auth API",
        work_order_type="api_endpoint",
        source_root=REPO_ROOT,
    )
    assert result["ok"] is True
    work_order_id = result["work_order_id"]

    row = _fetch_row(db_path, "business_work_orders", "work_order_id", work_order_id)
    assert (
        row is not None
    ), "business_work_orders row must be queryable on return (no daemon dependency)"
    assert row["title"] == "WO — Build auth API"
    assert row["milestone_id"] == milestone_id


# ---------------------------------------------------------------------------
# 6. create_task reads WO milestone_id correctly (Pattern C guarantee)
# ---------------------------------------------------------------------------


def test_create_task_resolves_milestone_id_from_materialised_wo(sdlc_env):
    from core.work_orders.mutations import create_task, create_work_order

    db_path = sdlc_env["db"]
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    _direct_insert_project(db_path, project_id)

    wo_result = create_work_order(
        project_id=project_id,
        milestone_id=milestone_id,
        title="WO — DB schema",
        work_order_type="infrastructure",
        source_root=REPO_ROOT,
    )
    assert wo_result["ok"] is True
    work_order_id = wo_result["work_order_id"]

    # WO must be in business_work_orders BEFORE create_task is called
    wo_row = _fetch_row(db_path, "business_work_orders", "work_order_id", work_order_id)
    assert wo_row is not None, "WO must be materialised before create_task can read milestone_id"
    assert wo_row["milestone_id"] == milestone_id

    task_result = create_task(
        work_order_id=work_order_id,
        project_id=project_id,
        title="Write migration 102",
        source_root=REPO_ROOT,
    )
    assert task_result["ok"] is True
    task_id = task_result["task_id"]

    task_row = _fetch_row(db_path, "business_tasks", "task_id", task_id)
    assert task_row is not None, "business_tasks row must be queryable on return"
    assert task_row["work_order_id"] == work_order_id
    assert task_row["title"] == "Write migration 102"


# ---------------------------------------------------------------------------
# 7. Full E2E chain: project → milestone → WO → task, all queryable on return
# ---------------------------------------------------------------------------


def test_full_sdlc_chain_all_rows_queryable_on_return(sdlc_env):
    """End-to-end materialization guarantee — no direct-SQL fixture shortcuts.

    Calls SDLC creators through their public API. After each call the
    corresponding read-model row must be queryable without manual ingest
    or daemon intervention.
    """
    from core.milestones.mutations import create_milestone
    from core.work_orders.mutations import create_task, create_work_order

    db_path = sdlc_env["db"]
    project_id = str(uuid.uuid4())

    # Step 1 — project (register_project does direct SQL; row is immediate)
    _direct_insert_project(db_path, project_id, name="E2E Test Project")
    proj_row = _fetch_row(db_path, "business_projects", "project_id", project_id)
    assert proj_row is not None, "project row must exist after direct insert"

    # Step 2 — milestone (event + sync_tick)
    ms_result = create_milestone(
        project_id=project_id,
        title="M1 — Core substrate",
        description="First deliverable",
        order_index=1,
        source_root=REPO_ROOT,
    )
    assert ms_result["ok"] is True, f"create_milestone failed: {ms_result}"
    ms_id = ms_result["milestone_id"]
    ms_row = _fetch_row(db_path, "business_milestones", "milestone_id", ms_id)
    assert ms_row is not None, "milestone row queryable immediately after create_milestone"
    assert ms_row["project_id"] == project_id
    assert ms_row["title"] == "M1 — Core substrate"

    # Step 3 — work order (event + sync_tick)
    wo_result = create_work_order(
        project_id=project_id,
        milestone_id=ms_id,
        title="WO — Projection tick",
        work_order_type="infrastructure",
        source_root=REPO_ROOT,
    )
    assert wo_result["ok"] is True, f"create_work_order failed: {wo_result}"
    wo_id = wo_result["work_order_id"]
    wo_row = _fetch_row(db_path, "business_work_orders", "work_order_id", wo_id)
    assert wo_row is not None, "WO row queryable immediately after create_work_order"
    assert wo_row["milestone_id"] == ms_id
    assert wo_row["project_id"] == project_id
    assert wo_row["title"] == "WO — Projection tick"

    # Step 4 — tasks (event + sync_tick, milestone_id resolved from materialised WO)
    task_titles = ["Add tick() to runner", "Wire sync_tick into creators", "Write E2E test"]
    task_ids = []
    for title in task_titles:
        t_result = create_task(
            work_order_id=wo_id,
            project_id=project_id,
            title=title,
            source_root=REPO_ROOT,
        )
        assert t_result["ok"] is True, f"create_task failed: {t_result}"
        task_ids.append(t_result["task_id"])

    for task_id in task_ids:
        t_row = _fetch_row(db_path, "business_tasks", "task_id", task_id)
        assert t_row is not None, f"task {task_id} must be queryable immediately"
        assert t_row["work_order_id"] == wo_id


# ---------------------------------------------------------------------------
# 8. check_sdlc_consistency() helper
# ---------------------------------------------------------------------------


def check_sdlc_consistency(db_path: Path) -> dict[str, Any]:
    """Report canonical creation events without corresponding read-model rows.

    Returns a dict with 'stranded_milestones', 'stranded_work_orders',
    'stranded_tasks' lists — each is a list of event_ids that have no
    matching row in the respective read-model table.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        stranded_ms = [row["event_id"] for row in conn.execute("""
                SELECT bce.event_id
                FROM business_canonical_events bce
                WHERE bce.event_type = 'milestone.created'
                  AND bce.milestone_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM business_milestones bm
                      WHERE bm.milestone_id = bce.milestone_id
                  )
                """).fetchall()]
        stranded_wo = [row["event_id"] for row in conn.execute("""
                SELECT bce.event_id
                FROM business_canonical_events bce
                WHERE bce.event_type = 'work_order.created'
                  AND bce.work_order_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM business_work_orders bwo
                      WHERE bwo.work_order_id = bce.work_order_id
                  )
                """).fetchall()]
        stranded_tasks = [row["event_id"] for row in conn.execute("""
                SELECT bce.event_id
                FROM business_canonical_events bce
                WHERE bce.event_type = 'task.created'
                  AND bce.task_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM business_tasks bt
                      WHERE bt.task_id = bce.task_id
                  )
                """).fetchall()]
    finally:
        conn.close()

    return {
        "stranded_milestones": stranded_ms,
        "stranded_work_orders": stranded_wo,
        "stranded_tasks": stranded_tasks,
        "total_stranded": len(stranded_ms) + len(stranded_wo) + len(stranded_tasks),
    }


def test_consistency_helper_reports_stranded_events(sdlc_env):
    """check_sdlc_consistency() correctly identifies events without read-model rows."""
    from datetime import datetime, timezone

    db_path = sdlc_env["db"]
    project_id = str(uuid.uuid4())
    _direct_insert_project(db_path, project_id)

    # Insert a canonical event WITHOUT projecting it (simulates stranded event)
    orphan_ms_id = str(uuid.uuid4())
    orphan_event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "milestone.created",
        "event_timestamp": datetime.now(timezone.utc).isoformat(),
        "trace": {"project_id": project_id, "milestone_id": orphan_ms_id, "domain": "sdlc"},
        "payload": {"title": "Orphan milestone", "status": "pending"},
    }
    _insert_canonical_event(db_path, orphan_event)

    report = check_sdlc_consistency(db_path)
    assert len(report["stranded_milestones"]) == 1
    assert report["total_stranded"] == 1


def test_consistency_clean_after_full_e2e_chain(sdlc_env):
    """After running the full E2E chain, consistency check reports zero stranded events."""
    from core.milestones.mutations import create_milestone
    from core.work_orders.mutations import create_task, create_work_order

    db_path = sdlc_env["db"]
    project_id = str(uuid.uuid4())
    _direct_insert_project(db_path, project_id)

    ms_result = create_milestone(project_id=project_id, title="M1", source_root=REPO_ROOT)
    wo_result = create_work_order(
        project_id=project_id,
        milestone_id=ms_result["milestone_id"],
        title="WO",
        source_root=REPO_ROOT,
    )
    create_task(
        work_order_id=wo_result["work_order_id"],
        project_id=project_id,
        title="T1",
        source_root=REPO_ROOT,
    )

    report = check_sdlc_consistency(db_path)
    assert (
        report["total_stranded"] == 0
    ), f"Consistency check found stranded events after full chain: {report}"
