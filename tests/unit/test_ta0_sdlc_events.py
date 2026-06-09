"""TA0 — SDLC entity creation events.

Tests that forward-emission and backfill migration produce correct canonical
events with the expected trace shape, attribution_status, and idempotency.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db() -> tuple[sqlite3.Connection, Path]:
    """Return an in-memory-like temp DB with minimal SDLC tables."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
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
        );
        CREATE TABLE IF NOT EXISTS business_projects (
            project_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS business_milestones (
            milestone_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            due_date TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            order_index INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            stage_gate_json TEXT,
            validation_expectations_json TEXT,
            security_readiness_checks_json TEXT
        );
        CREATE TABLE IF NOT EXISTS business_work_orders (
            work_order_id TEXT PRIMARY KEY,
            project_id TEXT,
            milestone_id TEXT,
            title TEXT,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'created',
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
        CREATE TABLE IF NOT EXISTS business_tasks (
            task_id TEXT PRIMARY KEY,
            work_order_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ds_projects (
            project_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ds_milestones (
            milestone_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            due_date TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            order_index INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ds_work_orders (
            work_order_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            milestone_id TEXT,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            work_order_type TEXT,
            block_reason TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)
    conn.commit()
    return conn, db_path


def _seed_project(conn: sqlite3.Connection) -> str:
    pid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO business_projects (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?, 'Test Project', 'desc', 'active', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')",
        (pid,),
    )
    conn.execute(
        "INSERT INTO ds_projects (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?, 'Test Project', 'desc', 'active', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')",
        (pid,),
    )
    conn.commit()
    return pid


def _seed_milestone(conn: sqlite3.Connection, project_id: str) -> str:
    mid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO business_milestones (milestone_id, project_id, title, status, created_at, updated_at)"
        " VALUES (?, ?, 'M1', 'pending', '2026-01-02T00:00:00+00:00', '2026-01-02T00:00:00+00:00')",
        (mid, project_id),
    )
    conn.execute(
        "INSERT INTO ds_milestones (milestone_id, project_id, title, status, created_at, updated_at)"
        " VALUES (?, ?, 'M1', 'pending', '2026-01-02T00:00:00+00:00', '2026-01-02T00:00:00+00:00')",
        (mid, project_id),
    )
    conn.commit()
    return mid


def _seed_work_order(conn: sqlite3.Connection, project_id: str, milestone_id: str) -> str:
    wid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, status, work_order_type, created_at, updated_at)"
        " VALUES (?, ?, ?, 'WO1', 'created', 'feature', '2026-01-03T00:00:00+00:00', '2026-01-03T00:00:00+00:00')",
        (wid, project_id, milestone_id),
    )
    conn.execute(
        "INSERT INTO ds_work_orders"
        " (work_order_id, project_id, milestone_id, title, status, work_order_type, created_at, updated_at)"
        " VALUES (?, ?, ?, 'WO1', 'open', 'feature', '2026-01-03T00:00:00+00:00', '2026-01-03T00:00:00+00:00')",
        (wid, project_id, milestone_id),
    )
    conn.commit()
    return wid


def _run_backfill_sql(conn: sqlite3.Connection) -> None:
    sql_path = (
        Path(__file__).parent.parent.parent
        / "core"
        / "event_store"
        / "migrations"
        / "061_backfill_sdlc_creation_events.sql"
    )
    conn.executescript(sql_path.read_text(encoding="utf-8"))
    conn.commit()


def _captured_events(spool_root: Path) -> list[dict]:
    events = []
    for f in spool_root.glob("*.json"):
        events.append(json.loads(f.read_text(encoding="utf-8")))
    return events


# ---------------------------------------------------------------------------
# Unit tests — emitter envelope shape
# ---------------------------------------------------------------------------


class TestProjectCreatedEnvelope:
    def test_correct_event_type(self, tmp_path):
        from canonical.events.envelope import CanonicalEventEnvelope

        env = CanonicalEventEnvelope(
            event_type="project.created",
            session_id=None,
            payload={"name": "Foo", "description": "", "status": "active"},
            severity="info",
            trace={
                "domain": "sdlc",
                "project_id": "p1",
                "attribution_status": "fully_attributed",
            },
        )
        d = env.to_dict()
        assert d["event_type"] == "project.created"
        assert d["trace"]["domain"] == "sdlc"
        assert d["trace"]["attribution_status"] == "fully_attributed"
        assert d["trace"]["project_id"] == "p1"
        assert d["payload"]["name"] == "Foo"
        assert "event_id" in d


class TestMilestoneCreatedEnvelope:
    def test_parent_project_id_in_trace(self):
        from canonical.events.envelope import CanonicalEventEnvelope

        env = CanonicalEventEnvelope(
            event_type="milestone.created",
            session_id=None,
            payload={"title": "M1", "status": "pending"},
            severity="info",
            trace={
                "domain": "sdlc",
                "project_id": "proj-abc",
                "milestone_id": "ms-xyz",
                "attribution_status": "fully_attributed",
            },
        )
        d = env.to_dict()
        assert d["trace"]["project_id"] == "proj-abc"
        assert d["trace"]["milestone_id"] == "ms-xyz"
        assert d["trace"]["attribution_status"] == "fully_attributed"


class TestWorkOrderCreatedEnvelope:
    def test_full_sdlc_trace(self):
        from canonical.events.envelope import CanonicalEventEnvelope

        env = CanonicalEventEnvelope(
            event_type="work_order.created",
            session_id=None,
            payload={"title": "WO1", "status": "open", "type": "feature"},
            severity="info",
            trace={
                "domain": "sdlc",
                "project_id": "proj-abc",
                "milestone_id": "ms-xyz",
                "work_order_id": "wo-123",
                "attribution_status": "fully_attributed",
            },
        )
        d = env.to_dict()
        assert d["trace"]["milestone_id"] == "ms-xyz"
        assert d["trace"]["work_order_id"] == "wo-123"
        assert d["trace"]["attribution_status"] == "fully_attributed"


class TestProjectDeletedEnvelope:
    def test_cascade_counts_in_payload(self):
        from canonical.events.envelope import CanonicalEventEnvelope

        env = CanonicalEventEnvelope(
            event_type="project.deleted",
            session_id=None,
            payload={"cascade_milestones": 3, "cascade_work_orders": 7, "cascade_tasks": 12},
            severity="info",
            trace={
                "domain": "sdlc",
                "project_id": "p-del",
                "attribution_status": "fully_attributed",
            },
        )
        d = env.to_dict()
        assert d["payload"]["cascade_milestones"] == 3
        assert d["payload"]["cascade_work_orders"] == 7
        assert d["payload"]["cascade_tasks"] == 12


# ---------------------------------------------------------------------------
# Unit tests — backfill migration
# ---------------------------------------------------------------------------


class TestBackfillMigration:
    def test_produces_events_for_all_rows(self):
        conn, _ = _make_db()
        pid = _seed_project(conn)
        mid = _seed_milestone(conn, pid)
        _seed_work_order(conn, pid, mid)

        _run_backfill_sql(conn)

        rows = conn.execute(
            "SELECT event_type FROM canonical_events ORDER BY event_type"
        ).fetchall()
        types = [r[0] for r in rows]
        assert "project.created" in types
        assert "milestone.created" in types
        assert "work_order.created" in types

    def test_backfill_events_have_backfill_attribution_status(self):
        conn, _ = _make_db()
        pid = _seed_project(conn)
        _seed_milestone(conn, pid)

        _run_backfill_sql(conn)

        rows = conn.execute(
            "SELECT trace FROM canonical_events WHERE event_type IN ('project.created','milestone.created')"
        ).fetchall()
        assert rows, "no rows found"
        for (trace_json,) in rows:
            trace = json.loads(trace_json)
            assert trace["attribution_status"] == "backfill", f"expected backfill, got: {trace}"

    def test_idempotent_run_twice(self):
        conn, _ = _make_db()
        pid = _seed_project(conn)
        mid = _seed_milestone(conn, pid)
        _seed_work_order(conn, pid, mid)

        _run_backfill_sql(conn)
        count_first = conn.execute("SELECT COUNT(*) FROM canonical_events").fetchone()[0]

        _run_backfill_sql(conn)
        count_second = conn.execute("SELECT COUNT(*) FROM canonical_events").fetchone()[0]

        assert (
            count_first == count_second
        ), f"Idempotency violated: {count_first} → {count_second} after second run"

    def test_backfill_count_matches_row_count(self):
        conn, _ = _make_db()
        pid = _seed_project(conn)
        mid1 = _seed_milestone(conn, pid)
        mid2 = _seed_milestone(conn, pid)
        _seed_work_order(conn, pid, mid1)
        _seed_work_order(conn, pid, mid2)
        _seed_work_order(conn, pid, mid2)

        _run_backfill_sql(conn)

        proj_events = conn.execute(
            "SELECT COUNT(*) FROM canonical_events WHERE event_type='project.created'"
        ).fetchone()[0]
        ms_events = conn.execute(
            "SELECT COUNT(*) FROM canonical_events WHERE event_type='milestone.created'"
        ).fetchone()[0]
        wo_events = conn.execute(
            "SELECT COUNT(*) FROM canonical_events WHERE event_type='work_order.created'"
        ).fetchone()[0]

        assert proj_events == 1
        assert ms_events == 2
        assert wo_events == 3


# ---------------------------------------------------------------------------
# Integration tests — forward emission via mutation call sites
# ---------------------------------------------------------------------------


class TestForwardEmissionIntegration:
    def _patch_spool(self, tmp_path: Path):
        """Patch spool.writer so events land in tmp_path files instead of real spool."""
        captured: list[dict] = []

        def fake_write_event(d, root=None):
            captured.append(d)

        return fake_write_event, captured

    def test_register_project_emits_project_created(self, tmp_path):
        conn, db_path = _make_db()
        captured: list[dict] = []

        def fake_write(d, root=None):
            captured.append(d)

        with (
            patch("core.projects.mutations._require_db", return_value=db_path),
            patch("spool.writer.write_event", side_effect=fake_write),
        ):
            from core.projects.mutations import register_project

            result = register_project(
                name="Integration Project",
                description="test",
                source_root=tmp_path,
            )

        assert result["ok"] is True
        assert any(
            e["event_type"] == "project.created" for e in captured
        ), f"project.created not found in captured: {[e['event_type'] for e in captured]}"
        created = next(e for e in captured if e["event_type"] == "project.created")
        assert created["trace"]["domain"] == "sdlc"
        assert created["trace"]["project_id"] == result["project_id"]
        assert created["trace"]["attribution_status"] == "fully_attributed"
        assert created["payload"]["name"] == "Integration Project"

    def test_create_work_order_emits_with_full_sdlc_trace(self, tmp_path):
        conn, db_path = _make_db()
        pid = _seed_project(conn)
        mid = _seed_milestone(conn, pid)
        captured: list[dict] = []

        def fake_write(d, root=None):
            captured.append(d)

        with (
            patch("core.work_orders.mutations._require_db", return_value=db_path),
            patch("spool.writer.write_event", side_effect=fake_write),
        ):
            from core.work_orders.mutations import create_work_order

            result = create_work_order(
                project_id=pid,
                milestone_id=mid,
                title="WO Integration Test",
                work_order_type="feature",
                source_root=tmp_path,
            )

        assert result["ok"] is True
        wo_events = [e for e in captured if e["event_type"] == "work_order.created"]
        assert wo_events, "work_order.created not emitted"
        ev = wo_events[0]
        assert ev["trace"]["project_id"] == pid
        assert ev["trace"]["milestone_id"] == mid
        assert ev["trace"]["work_order_id"] == result["work_order_id"]
        assert ev["trace"]["attribution_status"] == "fully_attributed"

    def test_work_order_started_trace_includes_milestone_id(self, tmp_path):
        """work_order.started trace now carries milestone_id after TA0 update."""
        from core.work_orders.start import start_work_order

        brief = {
            "ok": True,
            "work_order_id": "wo-test",
            "title": "Test WO",
            "type_id": "feature",
            "project_id": "proj-test",
            "milestone_id": "ms-test",
            "milestone_title": "M1",
            "status": "open",
            "pre_gate": None,
            "post_gate": None,
            "build_exec": None,
            "workflow_template": None,
            "precondition_skill": None,
            "brief_locked": None,
            "brief_warning": False,
            "pending_tasks": [],
            "gotchas": [],
            "blocking_milestone_count": 0,
            "label": "Feature",
            "marker_project_id": None,
            "project_name": "Test Project",
        }

        captured: list[dict] = []

        def fake_write(d, root=None):
            captured.append(d)

        conn, db_path = _make_db()

        with (
            patch("core.work_orders.start._require_db", return_value=db_path),
            patch("core.work_orders.start.read_work_order_brief", return_value=brief),
            patch(
                "core.work_orders.start.write_work_order_context", return_value=tmp_path / "ctx.md"
            ),
            patch("spool.writer.write_event", side_effect=fake_write),
        ):
            conn.execute(
                "INSERT INTO business_work_orders"
                " (work_order_id, project_id, milestone_id, title, status, work_order_type, created_at, updated_at)"
                " VALUES ('wo-test','proj-test','ms-test','Test WO','created','feature','2026-01-01','2026-01-01')"
            )
            conn.commit()
            start_work_order(
                work_order_id="wo-test",
                source_root=tmp_path,
                brief_data=brief,
            )

        started = [e for e in captured if e["event_type"] == "work_order.started"]
        assert started, "work_order.started not emitted"
        assert started[0]["trace"]["milestone_id"] == "ms-test"
        assert started[0]["trace"]["attribution_status"] == "fully_attributed"
