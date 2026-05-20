"""End-to-end integration tests for WorkflowRunner via CLI (dry_run only).

All tests use tmp_path for state isolation and dry_run=True so no real
skills are ever invoked. DB operations stay in tmp_path.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from control.execution.workflow.runner import WorkflowRunner, resolve_specifier
from control.execution.workflow.state import _read_state, _write_state

# ── Helpers ───────────────────────────────────────────────────────────────────


def _write_wf_yaml(tmp_path: Path, nodes: list[dict]) -> Path:
    yaml_path = tmp_path / "test_wf.yaml"
    node_lines = []
    for n in nodes:
        deps = n.get("depends_on", [])
        dep_str = f"\n    depends_on: [{', '.join(deps)}]" if deps else ""
        node_lines.append(f"  - id: {n['id']}\n    skill: {n.get('skill', 'plan')}{dep_str}")
    yaml_path.write_text(
        "name: test-wf\nnodes:\n" + "\n".join(node_lines),
        encoding="utf-8",
    )
    return yaml_path


def _bootstrap_state(tmp_path: Path, wf_key: str, yaml_path: Path, node_ids: list[str]) -> Path:
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "schema_version": 1,
        "active_workflows": {
            wf_key: {
                "workflow": "test-wf",
                "started": "2026-01-01T00:00:00+00:00",
                "status": "running",
                "yaml_path": str(yaml_path),
                "current_node": None,
                "nodes": {nid: {"status": "pending"} for nid in node_ids},
                "completed_nodes": [],
                "gates_passed": [],
                "gates_pending": [],
            }
        },
    }
    (state_dir / "workflows.json").write_text(json.dumps(state), encoding="utf-8")
    return state_dir


# ── E2E: single-node workflow ─────────────────────────────────────────────────


def test_runner_completes_single_node_workflow(tmp_path):
    """A workflow with one node reaches 'completed' status after run()."""
    yaml_path = _write_wf_yaml(tmp_path, [{"id": "n1", "skill": "plan"}])
    state_dir = _bootstrap_state(tmp_path, "wf-e2e-1", yaml_path, ["n1"])

    with patch("control.execution.workflow.runner.paths") as mock_paths:
        mock_paths.state_dir.return_value = state_dir
        runner = WorkflowRunner("wf-e2e-1", dry_run=True)
        final = runner.run()

    assert final == "completed"
    state = json.loads((state_dir / "workflows.json").read_text())
    wf = state["active_workflows"]["wf-e2e-1"]
    assert wf["status"] == "completed"
    assert wf["nodes"]["n1"]["status"] == "completed"


def test_runner_two_node_chain_both_complete(tmp_path):
    """A → B dependency chain: both nodes complete, final status is 'completed'."""
    yaml_path = _write_wf_yaml(
        tmp_path,
        [
            {"id": "a", "skill": "plan"},
            {"id": "b", "skill": "build", "depends_on": ["a"]},
        ],
    )
    state_dir = _bootstrap_state(tmp_path, "wf-e2e-2", yaml_path, ["a", "b"])

    with patch("control.execution.workflow.runner.paths") as mock_paths:
        mock_paths.state_dir.return_value = state_dir
        runner = WorkflowRunner("wf-e2e-2", dry_run=True)
        final = runner.run()

    assert final == "completed"
    state = json.loads((state_dir / "workflows.json").read_text())
    nodes = state["active_workflows"]["wf-e2e-2"]["nodes"]
    assert nodes["a"]["status"] == "completed"
    assert nodes["b"]["status"] == "completed"


def test_runner_three_node_parallel_wave(tmp_path):
    """Three independent nodes all complete in one wave."""
    yaml_path = _write_wf_yaml(
        tmp_path,
        [
            {"id": "x", "skill": "plan"},
            {"id": "y", "skill": "build"},
            {"id": "z", "skill": "verify"},
        ],
    )
    state_dir = _bootstrap_state(tmp_path, "wf-e2e-3", yaml_path, ["x", "y", "z"])

    with patch("control.execution.workflow.runner.paths") as mock_paths:
        mock_paths.state_dir.return_value = state_dir
        runner = WorkflowRunner("wf-e2e-3", dry_run=True)
        final = runner.run()

    assert final == "completed"
    state = json.loads((state_dir / "workflows.json").read_text())
    nodes = state["active_workflows"]["wf-e2e-3"]["nodes"]
    for nid in ("x", "y", "z"):
        assert nodes[nid]["status"] == "completed"


# ── E2E: specifier resolution in real YAML ───────────────────────────────────


def test_runner_resolves_bare_plan_to_ds_core(tmp_path):
    """Node with skill: plan resolves to ds-core:plan during execution."""
    yaml_path = _write_wf_yaml(tmp_path, [{"id": "n1", "skill": "plan"}])
    state_dir = _bootstrap_state(tmp_path, "wf-spec-1", yaml_path, ["n1"])

    invoked: list[str] = []

    def fake_invoke(self, specifier: str, node_id: str):
        invoked.append(specifier)
        return True, "[dry_run]"

    with patch("control.execution.workflow.runner.paths") as mock_paths:
        mock_paths.state_dir.return_value = state_dir
        with patch.object(WorkflowRunner, "_invoke_skill", fake_invoke):
            runner = WorkflowRunner("wf-spec-1", dry_run=False)
            runner.run()

    assert invoked == ["ds-core:plan"]


def test_runner_resolves_bare_debug_to_ds_quality(tmp_path):
    yaml_path = _write_wf_yaml(tmp_path, [{"id": "n1", "skill": "debug"}])
    state_dir = _bootstrap_state(tmp_path, "wf-spec-2", yaml_path, ["n1"])

    invoked: list[str] = []

    def fake_invoke(self, specifier: str, node_id: str):
        invoked.append(specifier)
        return True, "[fake]"

    with patch("control.execution.workflow.runner.paths") as mock_paths:
        mock_paths.state_dir.return_value = state_dir
        with patch.object(WorkflowRunner, "_invoke_skill", fake_invoke):
            runner = WorkflowRunner("wf-spec-2", dry_run=False)
            runner.run()

    assert invoked == ["ds-quality:debug"]


# ── E2E: node failure propagates ─────────────────────────────────────────────


def test_runner_failed_node_sets_completed_with_failures(tmp_path):
    """When a node fails, the workflow reaches 'completed_with_failures'."""
    yaml_path = _write_wf_yaml(tmp_path, [{"id": "n1", "skill": "plan"}])
    state_dir = _bootstrap_state(tmp_path, "wf-fail-1", yaml_path, ["n1"])

    def fake_invoke(self, specifier: str, node_id: str):
        return False, "simulated failure"

    with patch("control.execution.workflow.runner.paths") as mock_paths:
        mock_paths.state_dir.return_value = state_dir
        with patch.object(WorkflowRunner, "_invoke_skill", fake_invoke):
            runner = WorkflowRunner("wf-fail-1", dry_run=False)
            final = runner.run()

    assert final in ("completed_with_failures", "blocked")
    state = json.loads((state_dir / "workflows.json").read_text())
    assert state["active_workflows"]["wf-fail-1"]["nodes"]["n1"]["status"] == "failed"


# ── CLI smoke tests ───────────────────────────────────────────────────────────


def test_cli_workflow_start_help():
    """ds workflow start --help exits 0."""
    result = subprocess.run(
        [sys.executable, "-m", "interfaces.cli.ds", "workflow", "start", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "yaml_path" in result.stdout


def test_cli_workflow_advance_help():
    result = subprocess.run(
        [sys.executable, "-m", "interfaces.cli.ds", "workflow", "advance", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "dry-run" in result.stdout


def test_cli_workflow_list_help():
    result = subprocess.run(
        [sys.executable, "-m", "interfaces.cli.ds", "workflow", "list", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
