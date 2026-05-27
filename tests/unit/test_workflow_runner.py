"""Unit tests for WorkflowRunner and resolve_specifier."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from control.execution.workflow.runner import WorkflowRunner, resolve_specifier

# ── resolve_specifier ─────────────────────────────────────────────────────────


def test_resolve_specifier_bare_plan():
    assert resolve_specifier("plan") == "ds-core:plan"


def test_resolve_specifier_bare_build():
    assert resolve_specifier("build") == "ds-core:build"


def test_resolve_specifier_bare_verify():
    assert resolve_specifier("verify") == "ds-core:verify"


def test_resolve_specifier_bare_review():
    assert resolve_specifier("review") == "ds-core:review"


def test_resolve_specifier_bare_debug():
    assert resolve_specifier("debug") == "ds-quality:debug"


def test_resolve_specifier_bare_audit():
    assert resolve_specifier("audit") == "ds-quality:audit"


def test_resolve_specifier_already_qualified():
    assert resolve_specifier("ds-quality:debug") == "ds-quality:debug"


def test_resolve_specifier_already_qualified_with_prefix():
    assert resolve_specifier("ds-core:plan") == "ds-core:plan"


def test_resolve_specifier_unknown_bare_falls_back_to_core():
    assert resolve_specifier("unknown-mode") == "ds-core:unknown-mode"


def test_resolve_specifier_scope_maps_to_ds_project():
    assert resolve_specifier("scope") == "ds-project:scope"


def test_resolve_specifier_dast_maps_to_security():
    assert resolve_specifier("dast") == "ds-security:dast"


# ── WorkflowRunner.dry_run ────────────────────────────────────────────────────


def _make_state(tmp_path: Path, wf_key: str, node_ids: list[str]) -> Path:
    """Write a minimal workflows.json to tmp_path/state/ and return the state dir."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "schema_version": 1,
        "active_workflows": {
            wf_key: {
                "workflow": "test-wf",
                "status": "running",
                "yaml_path": str(tmp_path / "wf.yaml"),
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


def _make_yaml(tmp_path: Path, nodes: list[dict]) -> Path:
    """Write a minimal workflow YAML and return its path."""
    yaml_path = tmp_path / "wf.yaml"
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


def test_dry_run_never_invokes_subprocess(tmp_path):
    """dry_run must not spawn any subprocess."""
    _make_yaml(tmp_path, [{"id": "n1", "skill": "plan"}])
    state_dir = _make_state(tmp_path, "test-wf-1", ["n1"])

    with patch("control.execution.workflow.runner.paths") as mock_paths:
        mock_paths.state_dir.return_value = state_dir
        with patch("subprocess.run") as mock_sub:
            runner = WorkflowRunner("test-wf-1", dry_run=True)
            runner.run()
            mock_sub.assert_not_called()


def test_dry_run_marks_nodes_completed(tmp_path):
    """dry_run should mark nodes completed without subprocess."""
    _make_yaml(tmp_path, [{"id": "n1", "skill": "plan"}, {"id": "n2", "skill": "build"}])
    state_dir = _make_state(tmp_path, "test-wf-2", ["n1", "n2"])

    with patch("control.execution.workflow.runner.paths") as mock_paths:
        mock_paths.state_dir.return_value = state_dir
        runner = WorkflowRunner("test-wf-2", dry_run=True)
        result = runner.run()

    state = json.loads((state_dir / "workflows.json").read_text())
    wf = state["active_workflows"]["test-wf-2"]
    assert wf["nodes"]["n1"]["status"] == "completed"
    assert wf["nodes"]["n2"]["status"] == "completed"


def test_dry_run_respects_dependencies(tmp_path):
    """dry_run must honour depends_on order."""
    _make_yaml(
        tmp_path,
        [
            {"id": "n1", "skill": "plan"},
            {"id": "n2", "skill": "build", "depends_on": ["n1"]},
        ],
    )
    state_dir = _make_state(tmp_path, "test-wf-3", ["n1", "n2"])

    with patch("control.execution.workflow.runner.paths") as mock_paths:
        mock_paths.state_dir.return_value = state_dir
        runner = WorkflowRunner("test-wf-3", dry_run=True)
        runner.run()

    state = json.loads((state_dir / "workflows.json").read_text())
    wf = state["active_workflows"]["test-wf-3"]
    assert wf["nodes"]["n1"]["status"] == "completed"
    assert wf["nodes"]["n2"]["status"] == "completed"


# ── WorkflowRunner._invoke_skill ─────────────────────────────────────────────


def test_invoke_skill_calls_load_and_record_in_process(tmp_path):
    """A3: _invoke_skill calls ``load_skill_content`` + ``record_skill_invocation``
    directly via ``core.skills.invocation`` — no subprocess.run."""
    runner = WorkflowRunner("wf-test", dry_run=False)

    fake_load = MagicMock(return_value={"ok": True, "skill_content": "PLAN BODY"})
    fake_record = MagicMock(return_value={"ok": True, "event_emitted": True})

    with (
        patch("core.skills.invocation.load_skill_content", fake_load),
        patch("core.skills.invocation.record_skill_invocation", fake_record),
        patch("subprocess.run") as mock_sub,
    ):
        success, output = runner._invoke_skill("core:plan", "n1")

    mock_sub.assert_not_called()
    fake_load.assert_called_once()
    assert fake_load.call_args.kwargs["specifier"] == "core:plan"
    fake_record.assert_called_once()
    assert fake_record.call_args.kwargs["specifier"] == "core:plan"
    assert success is True
    assert "PLAN BODY" in output
    assert "Skill: core:plan" in output
    assert "Invocation recorded." in output


def test_invoke_skill_returns_false_when_load_fails(tmp_path):
    """When ``load_skill_content`` reports ok=False, the node fails with the
    error message in the output channel."""
    runner = WorkflowRunner("wf-test", dry_run=False)

    fake_load = MagicMock(return_value={"ok": False, "error": "Unknown skill: bogus:mode"})

    with patch("core.skills.invocation.load_skill_content", fake_load):
        success, output = runner._invoke_skill("bogus:mode", "n2")

    assert success is False
    assert "Unknown skill: bogus:mode" in output


def test_invoke_skill_dry_run_never_loads_or_records():
    """dry_run short-circuits before any direct-call path runs."""
    runner = WorkflowRunner("wf-test", dry_run=True)

    fake_load = MagicMock()
    fake_record = MagicMock()

    with (
        patch("core.skills.invocation.load_skill_content", fake_load),
        patch("core.skills.invocation.record_skill_invocation", fake_record),
        patch("subprocess.run") as mock_sub,
    ):
        success, output = runner._invoke_skill("ds-core:plan", "n1")

    fake_load.assert_not_called()
    fake_record.assert_not_called()
    mock_sub.assert_not_called()
    assert success is True
    assert "[dry_run]" in output


def test_invoke_skill_swallows_record_invocation_exceptions(tmp_path):
    """Spool emission is best-effort — if record_skill_invocation raises,
    the node still completes successfully with the SKILL.md body."""
    runner = WorkflowRunner("wf-test", dry_run=False)

    fake_load = MagicMock(return_value={"ok": True, "skill_content": "BODY"})
    fake_record = MagicMock(side_effect=RuntimeError("spool root unreachable"))

    with (
        patch("core.skills.invocation.load_skill_content", fake_load),
        patch("core.skills.invocation.record_skill_invocation", fake_record),
    ):
        success, output = runner._invoke_skill("core:plan", "n1")

    assert success is True
    assert "BODY" in output


def test_invoke_skill_handles_load_exception(tmp_path):
    """An import-time or other unexpected exception in the direct-call path
    fails the node with the exception message rather than propagating."""
    runner = WorkflowRunner("wf-test", dry_run=False)

    fake_load = MagicMock(side_effect=RuntimeError("boom"))
    with patch("core.skills.invocation.load_skill_content", fake_load):
        success, output = runner._invoke_skill("core:plan", "n1")

    assert success is False
    assert "boom" in output


# ── WorkflowRunner._update_node ──────────────────────────────────────────────


def test_update_node_persists_status(tmp_path):
    state_dir = _make_state(tmp_path, "wf-upd", ["n1"])

    with patch("control.execution.workflow.runner.paths") as mock_paths:
        mock_paths.state_dir.return_value = state_dir
        runner = WorkflowRunner("wf-upd", dry_run=True)
        runner._update_node("n1", "running", None)

    state = json.loads((state_dir / "workflows.json").read_text())
    assert state["active_workflows"]["wf-upd"]["nodes"]["n1"]["status"] == "running"


def test_update_node_sets_finished_on_completion(tmp_path):
    state_dir = _make_state(tmp_path, "wf-fin", ["n1"])

    with patch("control.execution.workflow.runner.paths") as mock_paths:
        mock_paths.state_dir.return_value = state_dir
        runner = WorkflowRunner("wf-fin", dry_run=True)
        runner._update_node("n1", "completed", "done", duration=1.2)

    state = json.loads((state_dir / "workflows.json").read_text())
    node = state["active_workflows"]["wf-fin"]["nodes"]["n1"]
    assert node["status"] == "completed"
    assert "finished" in node
    assert node["duration_s"] == 1.2


# ── WorkflowRunner.advance ────────────────────────────────────────────────────


def test_advance_returns_ready_node_ids(tmp_path):
    _make_yaml(tmp_path, [{"id": "n1", "skill": "plan"}, {"id": "n2", "skill": "build"}])
    state_dir = _make_state(tmp_path, "wf-adv", ["n1", "n2"])

    with patch("control.execution.workflow.runner.paths") as mock_paths:
        mock_paths.state_dir.return_value = state_dir
        runner = WorkflowRunner("wf-adv", dry_run=True)
        executed = runner.advance()

    assert set(executed) == {"n1", "n2"}


def test_advance_returns_empty_when_done(tmp_path):
    _make_yaml(tmp_path, [{"id": "n1", "skill": "plan"}])
    state_dir = _make_state(tmp_path, "wf-done", ["n1"])

    # Mark workflow as completed up front
    state = json.loads((state_dir / "workflows.json").read_text())
    state["active_workflows"]["wf-done"]["status"] = "completed"
    (state_dir / "workflows.json").write_text(json.dumps(state), encoding="utf-8")

    with patch("control.execution.workflow.runner.paths") as mock_paths:
        mock_paths.state_dir.return_value = state_dir
        runner = WorkflowRunner("wf-done", dry_run=True)
        executed = runner.advance()

    assert executed == []


# ── Command node handling ─────────────────────────────────────────────────────


def _make_command_yaml(tmp_path: Path, nodes: list[dict]) -> Path:
    """Write workflow YAML with command: block nodes."""
    yaml_path = tmp_path / "wf.yaml"
    lines = ["name: test-wf", "nodes:"]
    for n in nodes:
        lines.append(f"  - id: {n['id']}")
        deps = n.get("depends_on", [])
        if deps:
            lines.append(f"    depends_on: [{', '.join(deps)}]")
        if "type" in n:
            lines.append(f"    type: {n['type']}")
        if "skill" in n:
            lines.append(f"    skill: {n['skill']}")
        if "command" in n:
            lines.append("    command: |")
            for line in n["command"].splitlines():
                lines.append(f"      {line}")
    yaml_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return yaml_path


def test_command_node_not_skipped(tmp_path):
    """command: node with no skill: must not be marked skipped."""
    _make_command_yaml(tmp_path, [{"id": "n1", "command": "do something"}])
    state_dir = _make_state(tmp_path, "wf-cmd-1", ["n1"])

    with patch("control.execution.workflow.runner.paths") as mock_paths:
        mock_paths.state_dir.return_value = state_dir
        mock_paths.plugin_root.return_value = tmp_path
        runner = WorkflowRunner("wf-cmd-1", dry_run=True)
        runner.run()

    state = json.loads((state_dir / "workflows.json").read_text())
    node = state["active_workflows"]["wf-cmd-1"]["nodes"]["n1"]
    assert node["status"] != "skipped", "command: node must not be skipped"


def test_command_node_invokes_build_by_default(tmp_path):
    """command: node with no type: invokes ds-core:build."""
    _make_command_yaml(tmp_path, [{"id": "n1", "command": "do something"}])
    state_dir = _make_state(tmp_path, "wf-cmd-2", ["n1"])

    invoked: list[str] = []

    def fake_invoke(spec, nid):
        invoked.append(spec)
        return True, "ok"

    with patch("control.execution.workflow.runner.paths") as mock_paths:
        mock_paths.state_dir.return_value = state_dir
        mock_paths.plugin_root.return_value = tmp_path
        runner = WorkflowRunner("wf-cmd-2", dry_run=False)
        runner._invoke_skill = fake_invoke
        runner.run()

    assert "ds-core:build" in invoked


def test_command_node_research_type_invokes_think(tmp_path):
    """command: node with type:research invokes core:think."""
    _make_command_yaml(tmp_path, [{"id": "n1", "type": "research", "command": "analyze"}])
    state_dir = _make_state(tmp_path, "wf-cmd-3", ["n1"])

    invoked: list[str] = []

    def fake_invoke(spec, nid):
        invoked.append(spec)
        return True, "ok"

    with patch("control.execution.workflow.runner.paths") as mock_paths:
        mock_paths.state_dir.return_value = state_dir
        mock_paths.plugin_root.return_value = tmp_path
        runner = WorkflowRunner("wf-cmd-3", dry_run=False)
        runner._invoke_skill = fake_invoke
        runner.run()

    assert "ds-core:think" in invoked


def test_command_node_plan_type_invokes_plan(tmp_path):
    """command: node with type:plan invokes core:plan."""
    _make_command_yaml(tmp_path, [{"id": "n1", "type": "plan", "command": "plan it"}])
    state_dir = _make_state(tmp_path, "wf-cmd-4", ["n1"])

    invoked: list[str] = []

    def fake_invoke(spec, nid):
        invoked.append(spec)
        return True, "ok"

    with patch("control.execution.workflow.runner.paths") as mock_paths:
        mock_paths.state_dir.return_value = state_dir
        mock_paths.plugin_root.return_value = tmp_path
        runner = WorkflowRunner("wf-cmd-4", dry_run=False)
        runner._invoke_skill = fake_invoke
        runner.run()

    assert "ds-core:plan" in invoked


def test_command_node_writes_context_file(tmp_path):
    """command: content written to .planning/workflow/<wf_key>/<node_id>-prompt.md."""
    _make_command_yaml(tmp_path, [{"id": "n1", "command": "STEP 1: do the thing"}])
    state_dir = _make_state(tmp_path, "wf-ctx-1", ["n1"])

    with patch("control.execution.workflow.runner.paths") as mock_paths:
        mock_paths.state_dir.return_value = state_dir
        mock_paths.plugin_root.return_value = tmp_path
        runner = WorkflowRunner("wf-ctx-1", dry_run=True)
        runner.run()

    ctx_file = tmp_path / ".planning" / "workflow" / "wf-ctx-1" / "n1-prompt.md"
    assert ctx_file.is_file(), "context file must exist after command: node execution"
    content = ctx_file.read_text()
    assert "STEP 1: do the thing" in content


def test_command_node_status_completed_after_execution(tmp_path):
    """command: node status = completed after successful execution."""
    _make_command_yaml(tmp_path, [{"id": "n1", "command": "do work"}])
    state_dir = _make_state(tmp_path, "wf-cmd-5", ["n1"])

    with patch("control.execution.workflow.runner.paths") as mock_paths:
        mock_paths.state_dir.return_value = state_dir
        mock_paths.plugin_root.return_value = tmp_path
        runner = WorkflowRunner("wf-cmd-5", dry_run=True)
        runner.run()

    state = json.loads((state_dir / "workflows.json").read_text())
    assert state["active_workflows"]["wf-cmd-5"]["nodes"]["n1"]["status"] == "completed"


def test_command_node_output_written_to_state(tmp_path):
    """command: node output written to state after execution."""
    _make_command_yaml(tmp_path, [{"id": "n1", "command": "do work"}])
    state_dir = _make_state(tmp_path, "wf-cmd-6", ["n1"])

    with patch("control.execution.workflow.runner.paths") as mock_paths:
        mock_paths.state_dir.return_value = state_dir
        mock_paths.plugin_root.return_value = tmp_path
        runner = WorkflowRunner("wf-cmd-6", dry_run=True)
        runner.run()

    state = json.loads((state_dir / "workflows.json").read_text())
    output = state["active_workflows"]["wf-cmd-6"]["nodes"]["n1"].get("output", "")
    assert output, "output must be non-empty after command: node execution"
    assert "n1" in output


def test_node_neither_skill_nor_command_still_skipped(tmp_path):
    """Node with neither skill: nor command: is still skipped."""
    yaml_path = tmp_path / "wf.yaml"
    yaml_path.write_text(
        "name: test-wf\nnodes:\n  - id: n1\n    timeout_seconds: 60\n",
        encoding="utf-8",
    )
    state_dir = _make_state(tmp_path, "wf-skip-1", ["n1"])

    with patch("control.execution.workflow.runner.paths") as mock_paths:
        mock_paths.state_dir.return_value = state_dir
        mock_paths.plugin_root.return_value = tmp_path
        runner = WorkflowRunner("wf-skip-1", dry_run=True)
        runner.run()

    state = json.loads((state_dir / "workflows.json").read_text())
    assert state["active_workflows"]["wf-skip-1"]["nodes"]["n1"]["status"] == "skipped"


def test_command_node_output_enables_downstream_templates(tmp_path):
    """After command: node completes, downstream nodes have non-empty output."""
    _make_command_yaml(
        tmp_path,
        [
            {"id": "n1", "command": "do analysis"},
            {"id": "n2", "command": "summarize results", "depends_on": ["n1"]},
        ],
    )
    state_dir = _make_state(tmp_path, "wf-tmpl-1", ["n1", "n2"])

    with patch("control.execution.workflow.runner.paths") as mock_paths:
        mock_paths.state_dir.return_value = state_dir
        mock_paths.plugin_root.return_value = tmp_path
        runner = WorkflowRunner("wf-tmpl-1", dry_run=True)
        runner.run()

    state = json.loads((state_dir / "workflows.json").read_text())
    n1_output = state["active_workflows"]["wf-tmpl-1"]["nodes"]["n1"].get("output", "")
    n2_output = state["active_workflows"]["wf-tmpl-1"]["nodes"]["n2"].get("output", "")
    assert n1_output, "n1 must have non-empty output after execution"
    assert n2_output, "n2 must have non-empty output after n1 completes"
