"""Integration tests: workflow_state emits canonical completion events to the
spool on terminal runs and prunes JSON.

WO 9f47a1a0: raw_workflow_runs/raw_workflow_nodes (write-orphaned since
2026-05-18) dropped migration 141 — see
core/event_store/migrations/141_drop_orphaned_workflow_raw_tables.sql.
archive_workflow() is gone; control/execution/workflow/state.py now emits
workflow.completed / workflow.node.completed canonical events straight to the
spool (emitters/shared/spool_writer.py). last_run()/run_count() read
ai_canonical_events, which only reflects spool events after ingestion — tests
call spool.ingestor.ingest() explicitly, per the established canonical-event
test pattern (see test_workflow_research_decision_telemetry_emitters.py).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from control.execution.workflow import state as workflow_state  # noqa: E402
from core.event_store.studio_db import _connect, last_run, run_count  # noqa: E402
from spool.ingestor import ingest  # noqa: E402


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    from core.config import paths

    monkeypatch.setattr(paths, "state_dir", lambda: tmp_path)
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool"))
    # Pre-migrate so the ai_canonical_events schema (+ indexes) exists before
    # ingest() creates its target table lazily on first write.
    _connect(tmp_path / "studio.db").close()
    return tmp_path


def _seed(state_dir: Path, key: str, nodes: dict, wf_status: str = "running") -> None:
    wf = {
        "workflow": "wf",
        "yaml_path": "/x.yaml",
        "status": wf_status,
        "started": "2026-01-01T00:00:00+00:00",
        "current_node": None,
        "nodes": nodes,
        "completed_nodes": [],
        "gates_passed": [],
        "gates_pending": [],
    }
    p = state_dir / "workflows.json"
    p.write_text(json.dumps({"schema_version": 1, "active_workflows": {key: wf}}), encoding="utf-8")


def _active(state_dir: Path) -> dict:
    return json.loads((state_dir / "workflows.json").read_text(encoding="utf-8"))[
        "active_workflows"
    ]


def _spool_files(state_dir: Path) -> list[dict]:
    spool_dir = state_dir / "spool" / "spool"
    if not spool_dir.is_dir():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(spool_dir.glob("*.json"))]


def _ingest(state_dir: Path) -> None:
    """Project spooled canonical events into ai_canonical_events."""
    ingest(root=state_dir / "spool", db_path=state_dir / "studio.db")


class TestArchiveOnTerminal:
    def test_completed_pruned_from_json(self, state_dir):
        key = "wf-1"
        _seed(state_dir, key, {"n1": {"status": "pending"}})
        args = argparse.Namespace(
            key=key, node_id="n1", status="completed", output=None, duration=None
        )
        workflow_state.cmd_update(args)

        assert key not in _active(state_dir), "completed run must be pruned from JSON"

    def test_completed_archived_to_db(self, state_dir):
        key = "wf-2"
        _seed(state_dir, key, {"n1": {"status": "pending"}})
        args = argparse.Namespace(
            key=key, node_id="n1", status="completed", output=None, duration=None
        )
        workflow_state.cmd_update(args)
        _ingest(state_dir)

        db = state_dir / "studio.db"
        assert last_run("wf", db_path=db) is not None
        assert run_count("wf", db_path=db) == 1

    def test_completed_with_failures_archives(self, state_dir):
        key = "wf-3"
        _seed(state_dir, key, {"n1": {"status": "completed"}, "n2": {"status": "pending"}})
        args = argparse.Namespace(
            key=key, node_id="n2", status="failed", output=None, duration=None
        )
        workflow_state.cmd_update(args)
        _ingest(state_dir)

        assert key not in _active(state_dir), "completed_with_failures run must be pruned from JSON"
        assert last_run("wf", db_path=state_dir / "studio.db") is not None

    def test_abort_archives(self, state_dir):
        key = "wf-4"
        _seed(state_dir, key, {"n1": {"status": "running"}})
        args = argparse.Namespace(key=key)
        workflow_state.cmd_abort(args)
        _ingest(state_dir)

        assert key not in _active(state_dir), "aborted run must be pruned from JSON"
        db = state_dir / "studio.db"
        assert last_run("wf", db_path=db) is not None
        assert run_count("wf", db_path=db) == 1

    def test_non_terminal_update_stays_in_json(self, state_dir):
        key = "wf-5"
        _seed(state_dir, key, {"n1": {"status": "pending"}, "n2": {"status": "pending"}})
        args = argparse.Namespace(
            key=key, node_id="n1", status="completed", output=None, duration=None
        )
        workflow_state.cmd_update(args)
        _ingest(state_dir)

        assert key in _active(state_dir), "in-flight run must remain in JSON"
        assert last_run("wf", db_path=state_dir / "studio.db") is None


class TestCanonicalEventEmission:
    """WO 9f47a1a0: proves the emission fix — a terminal workflow run must land
    a workflow.completed canonical envelope in the spool, independent of any
    SQLite write succeeding."""

    def test_completed_run_emits_workflow_completed_envelope(self, state_dir):
        key = "wf-emit-1"
        _seed(state_dir, key, {"n1": {"status": "pending"}})
        args = argparse.Namespace(
            key=key, node_id="n1", status="completed", output="ok", duration=1.5
        )
        workflow_state.cmd_update(args)

        events = _spool_files(state_dir)
        completed = [e for e in events if e["event_type"] == "workflow.completed"]
        assert len(completed) == 1, f"expected exactly one workflow.completed envelope: {events}"
        envelope = completed[0]
        assert envelope["payload"]["workflow"] == "wf"
        assert envelope["payload"]["status"] == "completed"
        assert envelope["trace"] == {"domain": "telemetry", "workflow_id": "wf"}

        node_events = [e for e in events if e["event_type"] == "workflow.node.completed"]
        assert len(node_events) == 1
        assert node_events[0]["payload"]["node_id"] == "n1"
        assert node_events[0]["payload"]["workflow"] == "wf"

    def test_aborted_run_emits_workflow_completed_envelope(self, state_dir):
        key = "wf-emit-2"
        _seed(state_dir, key, {"n1": {"status": "running"}})
        args = argparse.Namespace(key=key)
        workflow_state.cmd_abort(args)

        events = _spool_files(state_dir)
        completed = [e for e in events if e["event_type"] == "workflow.completed"]
        assert len(completed) == 1
        assert completed[0]["payload"]["status"] == "aborted"

    def test_emitted_envelope_ingests_into_ai_canonical_events(self, state_dir):
        """End-to-end: spool write -> ingest -> ai_canonical_events row, with
        the exact payload shape workflow_collector.py / studio_db.last_run
        expect."""
        key = "wf-emit-3"
        _seed(state_dir, key, {"n1": {"status": "pending"}})
        args = argparse.Namespace(
            key=key, node_id="n1", status="completed", output=None, duration=None
        )
        workflow_state.cmd_update(args)
        _ingest(state_dir)

        conn = _connect(state_dir / "studio.db")
        try:
            row = conn.execute(
                "SELECT payload, workflow_id FROM ai_canonical_events"
                " WHERE event_type = 'workflow.completed'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row["workflow_id"] == "wf"
        payload = json.loads(row["payload"])
        assert payload["status"] == "completed"
        assert {"run_key", "workflow", "status", "started_at", "finished_at", "duration_ms"} <= set(
            payload
        )
