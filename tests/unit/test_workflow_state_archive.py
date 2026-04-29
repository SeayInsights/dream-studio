"""Integration tests: workflow_state archives terminal runs to studio.db and prunes JSON."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))

from lib import workflow_state  # noqa: E402
from lib.studio_db import last_run, run_count  # noqa: E402


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    from lib import paths
    monkeypatch.setattr(paths, "state_dir", lambda: tmp_path)
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
    return json.loads((state_dir / "workflows.json").read_text(encoding="utf-8"))["active_workflows"]


class TestArchiveOnTerminal:
    def test_completed_pruned_from_json(self, state_dir):
        key = "wf-1"
        _seed(state_dir, key, {"n1": {"status": "pending"}})
        args = argparse.Namespace(key=key, node_id="n1", status="completed", output=None, duration=None)
        workflow_state.cmd_update(args)

        assert key not in _active(state_dir), "completed run must be pruned from JSON"

    def test_completed_archived_to_db(self, state_dir):
        key = "wf-2"
        _seed(state_dir, key, {"n1": {"status": "pending"}})
        args = argparse.Namespace(key=key, node_id="n1", status="completed", output=None, duration=None)
        workflow_state.cmd_update(args)

        db = state_dir / "studio.db"
        assert last_run("wf", db_path=db) is not None
        assert run_count("wf", db_path=db) == 1

    def test_completed_with_failures_archives(self, state_dir):
        key = "wf-3"
        _seed(state_dir, key, {"n1": {"status": "completed"}, "n2": {"status": "pending"}})
        args = argparse.Namespace(key=key, node_id="n2", status="failed", output=None, duration=None)
        workflow_state.cmd_update(args)

        assert key not in _active(state_dir), "completed_with_failures run must be pruned from JSON"
        assert last_run("wf", db_path=state_dir / "studio.db") is not None

    def test_abort_archives(self, state_dir):
        key = "wf-4"
        _seed(state_dir, key, {"n1": {"status": "running"}})
        args = argparse.Namespace(key=key)
        workflow_state.cmd_abort(args)

        assert key not in _active(state_dir), "aborted run must be pruned from JSON"
        db = state_dir / "studio.db"
        assert last_run("wf", db_path=db) is not None
        assert run_count("wf", db_path=db) == 1

    def test_non_terminal_update_stays_in_json(self, state_dir):
        key = "wf-5"
        _seed(state_dir, key, {"n1": {"status": "pending"}, "n2": {"status": "pending"}})
        args = argparse.Namespace(key=key, node_id="n1", status="completed", output=None, duration=None)
        workflow_state.cmd_update(args)

        assert key in _active(state_dir), "in-flight run must remain in JSON"
        assert last_run("wf", db_path=state_dir / "studio.db") is None
