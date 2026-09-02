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


# -- WO-NODE-COMPLETION-EVIDENCE: a node is complete when its EFFECT is observable ---


def _runner_for_verification():
    """A runner instance whose only job is to answer _verify_completion.

    Constructed without __init__ because the method reads exactly one attribute and
    building a whole workflow to ask "is this node done" would test the harness, not the
    behaviour.
    """
    from control.execution.workflow.runner import WorkflowRunner

    r = WorkflowRunner.__new__(WorkflowRunner)
    r.dry_run = False
    return r


def test_a_node_without_an_observable_condition_is_not_reported_completed():
    """THE DEFECT THIS WORK ORDER EXISTS FOR.

    _invoke_skill loads a node's text and returns it with the footer "The AI reading this
    output has the skill instructions above and should now execute them". _execute_wave
    then set `status = "completed" if success else "failed"` -- where success meant the
    text LOADED. So a node was complete when its prompt was printed.

    Measured: all 14 nodes of execute-work-orders.yaml are prose-for-an-agent, and none is
    executable as written. A driver over that would march through fourteen nodes declaring
    success with no work done.
    """
    from control.execution.workflow.runner import WorkflowRunner

    status, reason = WorkflowRunner._verify_completion(_runner_for_verification(), "n1", {})

    assert status == "unverified", f"a node whose effect nobody observed reported {status!r}"
    assert status != "completed"
    assert reason and "never observed" in reason
    assert "completion_check" in reason, "the reason must name what would fix it"


def test_a_loaded_prompt_leaves_the_node_pending():
    """Task 2, stated as the runner sees it: loading is not completing. The wave must not
    reach "completed" for a node that only declares prose."""
    import inspect

    from control.execution.workflow.runner import WorkflowRunner

    src = inspect.getsource(WorkflowRunner._execute_wave)
    assert (
        '"completed" if success else "failed"' not in src
    ), "the wave still equates a successful LOAD with completion"
    assert "_verify_completion(" in src, "the wave must consult the completion check"


def test_an_unmet_condition_blocks_with_a_reason():
    """BLOCKED IS NOT FAILED. Failed means the work was attempted and went wrong; blocked
    means the effect is not there yet -- for a prose node, usually that the agent has not
    done it. A driver must stop at blocked without recording a failure."""
    from control.execution.workflow.runner import WorkflowRunner

    status, reason = WorkflowRunner._verify_completion(
        _runner_for_verification(),
        "n1",
        {"completion_check": "git rev-parse --verify no-such-ref-exists-here"},
    )

    assert status == "blocked", f"an unmet condition reported {status!r}"
    assert status != "failed", "the node was not attempted-and-broken; its effect is absent"
    assert reason and "exited" in reason, "the reason must name what was observed"
    assert "no-such-ref-exists-here" in reason, "and the check that was run"


def test_a_met_condition_completes():
    """The condition has to be satisfiable, or the gate is a wall rather than a check."""
    from control.execution.workflow.runner import WorkflowRunner

    status, reason = WorkflowRunner._verify_completion(
        _runner_for_verification(),
        "n1",
        {"completion_check": "git rev-parse --abbrev-ref HEAD"},
    )
    assert status == "completed"
    assert reason is None


def test_a_check_that_exits_zero_while_saying_the_wrong_thing_blocks():
    """The case completion_contains exists for. A gate can print "Overall: FAIL" and exit
    0; an exit code alone would read that as success -- the same
    absence-of-failure-is-not-evidence-of-success shape this milestone keeps finding."""
    from control.execution.workflow.runner import WorkflowRunner

    status, reason = WorkflowRunner._verify_completion(
        _runner_for_verification(),
        "n1",
        {
            "completion_check": "git rev-parse --abbrev-ref HEAD",
            "completion_contains": "a-branch-name-that-is-not-checked-out",
        },
    )
    assert status == "blocked"
    assert reason and "does not contain" in reason


def test_a_check_that_cannot_run_blocks_rather_than_completing():
    """An unrunnable check has proved nothing. Treating it as success would make a broken
    condition indistinguishable from a met one."""
    from control.execution.workflow.runner import WorkflowRunner

    status, reason = WorkflowRunner._verify_completion(
        _runner_for_verification(),
        "n1",
        {"completion_check": "this-command-does-not-exist-anywhere --please"},
    )
    assert status == "blocked"
    assert reason


def test_dry_run_still_marks_nodes_completed():
    """Dry run SIMULATES; nothing ran, so no condition can hold. Verifying one would make
    every dry run report blocked -- turning a planning tool into a wall. The simulation
    keeps its old meaning: this node WOULD complete."""
    from control.execution.workflow.runner import WorkflowRunner

    r = WorkflowRunner.__new__(WorkflowRunner)
    r.dry_run = True

    status, reason = WorkflowRunner._verify_completion(r, "n1", {})
    assert status == "completed"
    assert reason is None


def test_the_check_is_bounded():
    """A completion check observes an effect that already happened -- a git ref, a status
    query. It must be a cheap read, never the work itself, or the orchestrator's own
    timeout budget is spent proving what it just did."""
    from control.execution.workflow.runner import _COMPLETION_CHECK_TIMEOUT

    assert 0 < _COMPLETION_CHECK_TIMEOUT <= 120, _COMPLETION_CHECK_TIMEOUT


# -- WO-NODE-COMPLETION-EVIDENCE task 4: the driver stops where a human is needed ----


def test_the_driver_stops_at_a_blocked_node():
    """THE DRIVER ALREADY EXISTED. The task said to build `ds workflow run
    --until-blocked`; `ds workflow run` was already a loop that advances waves and
    returns when nothing is ready. What it could not do was say ANYTHING about why it
    stopped -- `cmd_run` printed "[workflow] final status: blocked" and exited 1.

    That is a status, not direction. It names no node, no reason, and nothing to do, so
    the loop hands back exactly the question the operator started with. A driver that
    stops without saying what it is waiting on has not taken the human out of the loop;
    it has moved them somewhere worse, because now they must reconstruct the state.
    """
    from control.execution.workflow.runner import WorkflowRunner

    r = WorkflowRunner.__new__(WorkflowRunner)
    described = WorkflowRunner._describe_blockage(
        r,
        {
            "capability-probe": {"status": "completed"},
            "run-gates": {
                "status": "blocked",
                "output": "…\n\n[completion] BLOCKED: the node did not report 'GATES: PASS'",
            },
            "create-branch": {"status": "pending"},
        },
    )

    assert "run-gates" in described, "the operator must be told WHICH node"
    assert "GATES: PASS" in described, "and what it was waiting for"
    assert "capability-probe" not in described, "a completed node is not what it waits on"
    assert "create-branch" not in described, "a pending downstream node is noise, not a blocker"


def test_a_blockage_with_no_blocking_node_says_so_rather_than_returning_empty():
    """An empty string would print as "[workflow] waiting on:" followed by nothing --
    the same non-answer in a longer form."""
    from control.execution.workflow.runner import WorkflowRunner

    r = WorkflowRunner.__new__(WorkflowRunner)
    described = WorkflowRunner._describe_blockage(r, {"a": {"status": "pending"}})
    assert described.strip()
    assert "cycle" in described


def test_unverified_satisfies_all_done_because_failed_does():
    """MY OWN DEFECT, found by asking what the statuses mean rather than what they do.

    `all_done` means "the dependency reached a terminal state, I do not care how it
    went". I added `unverified` without adding it here, which made unverified STRICTER
    than failed -- a stronger negative that this rule already accepts. `blocked` stays
    out on purpose: it is explicitly not-yet, and the effect may still arrive.
    """
    from control.execution.workflow.engine import _compute_ready_nodes

    ynodes = {"a": {"id": "a"}, "b": {"id": "b", "depends_on": ["a"], "trigger_rule": "all_done"}}

    def _ready(status):
        state = {"a": {"status": status}, "b": {"status": "pending"}}
        return _compute_ready_nodes(ynodes, state, {})[0]

    assert _ready("failed") == ["b"], "baseline: all_done accepts a failed dependency"
    assert _ready("unverified") == ["b"], "so it must accept a weaker negative too"
    assert _ready("blocked") == [], "but not-yet is not done"


def test_no_orchestrator_node_claims_an_observable_it_cannot_have():
    """CORRECTED AFTER AN INDEPENDENT REVIEW FOUND THE FIRST VERSION WRONG.

    I gave all 14 nodes a `completion_contains` naming the token their prompt tells the
    agent to print, and asserted here that every node declared an observable. It read as
    progress and was not: `_invoke_skill` LOADS a skill and returns its SKILL.md text, and
    `_execute_wave` then replaces a command node's output with "<id> executed via
    <specifier>". The runner never holds an agent's report, so those tokens could never
    match -- `ds workflow run` blocked unconditionally at node 1 of 14, which is a
    REGRESSION on marching through, not a fix.

    Worse, had the check been pointed at the loaded prompt instead, every token appears in
    its own prompt by construction, so every node would have "completed" by reading its own
    instructions -- the original defect with extra steps.

    A completion_contains with no completion_check is therefore inert, and an inert
    declaration is prose wearing a gate's clothes. The nodes are honestly `unverified`
    until someone writes checks that observe the effect from outside.
    """
    import yaml

    path = (
        Path(__file__).resolve().parents[2] / "canonical" / "workflows" / "execute-work-orders.yaml"
    )
    nodes = yaml.safe_load(path.read_text(encoding="utf-8"))["nodes"]
    assert nodes

    inert = [
        n["id"] for n in nodes if n.get("completion_contains") and not n.get("completion_check")
    ]
    assert inert == [], (
        f"these nodes declare a token nothing can check: {inert}. "
        f"completion_contains qualifies a completion_check's output; alone it verifies "
        f"nothing, and a declaration that verifies nothing is worse than an honest absence"
    )


def test_the_completion_decision_ignores_the_nodes_text_entirely():
    """CORRECTED TWICE, AND THE SECOND CORRECTION IS THE POINT.

    First cut: the completion check compared a declared token against the node's output,
    while _execute_wave had already replaced a command node's output with a synthetic
    "<id> executed via <specifier>" receipt. A review caught it.

    My fix threaded the real output through so the check would see it. A later review
    caught THAT: by then _verify_completion no longer read its `output` parameter at all,
    because the completion_contains-alone branch was gone. I had passed a value and
    asserted the passing, not the reading -- the same computed-and-discarded shape as the
    truncation note I dropped earlier this session.

    The honest property is stronger and simpler: this runner cannot see what an agent
    does, so the completion decision must not depend on any text the node produced. Only a
    completion_check subprocess, observing state from outside, is evidence.
    """
    import inspect

    from control.execution.workflow.runner import WorkflowRunner

    sig = inspect.signature(WorkflowRunner._verify_completion)
    assert list(sig.parameters) == ["self", "node_id", "ynode"], (
        f"_verify_completion takes {list(sig.parameters)} — a text parameter here can only "
        f"be the node's own report, which this runner never has"
    )

    body = inspect.getsource(WorkflowRunner._verify_completion)
    body = body.split(chr(34) * 3)[2]  # past the docstring
    for banned in ("raw_output", "expected in output", "in (output"):
        assert banned not in body, f"the decision is reading node text again: {banned!r}"


def test_the_orchestrator_declares_checks_that_observe_real_state():
    """WO e4e85949. Every node now either declares a completion_check that observes state
    OUTSIDE the runner, or records why it cannot.

    Each check here was RUN before it was written, because the two previous attempts were
    not. The first declared `completion_contains` tokens the runner can never see — it
    delivers a prompt and never holds the agent's output. The second invented
    `ds work-order tasks-remaining --active --quiet`, a command that does not exist.

    And the third nearly shipped: `implement-tasks` asked `ds project state` for the
    substring `"pending_tasks": 0,`, which appears THIRTY times in that output, once per
    work order in the ready set. It passed whenever any work order anywhere had nothing
    pending — a check that could not fail for the reason it existed. Running it is what
    caught that, which is why the assertion below names the script instead.
    """
    import yaml

    path = (
        Path(__file__).resolve().parents[2] / "canonical" / "workflows" / "execute-work-orders.yaml"
    )
    raw = path.read_text(encoding="utf-8")
    nodes = yaml.safe_load(raw)["nodes"]
    assert nodes

    by_id = {n["id"]: n for n in nodes}

    # A node without a check must SAY why. An unexplained gap reads as an oversight and
    # invites the next author to fill it with something invented.
    for node in nodes:
        if node.get("completion_check"):
            continue
        marker = f"- id: {node['id']}"
        start = raw.index(marker)
        window_end = start + 400
        window = raw[start:window_end]
        assert (
            "NO completion_check:" in window
        ), f"{node['id']} has no check and no recorded reason — the gap looks accidental"

    # The scoped check, not the substring that matched the whole ready set.
    implement = by_id["implement-tasks"]["completion_check"]
    assert "active_wo_tasks_complete.py" in implement, implement
    assert "pending_tasks" not in implement, (
        "implement-tasks is matching a substring of `ds project state` again; that marker "
        "appears once per work order in the ready set and cannot fail for this node"
    )
    script = Path(__file__).resolve().parents[2] / "scripts" / "active_wo_tasks_complete.py"
    assert script.is_file(), "the check names a script that does not exist"

    # A check must observe something outside the runner. `echo`-shaped checks assert
    # nothing; these each shell out to git, gh, or the authority.
    checked = [n for n in nodes if n.get("completion_check")]
    assert len(checked) >= 6, f"only {len(checked)} nodes declare a check"
    for node in checked:
        cmd = node["completion_check"]
        assert any(
            cmd.startswith(p) for p in ("git ", "gh ", "python ")
        ), f"{node['id']} declares {cmd!r}, which does not invoke an external observer"


# -- WO e4e85949: executing a node, inside the boundaries the operator set --------


def test_an_executing_node_that_pushes_is_caught_not_trusted():
    """OPERATOR RULING: "an executing node can't push."

    Telling an agent not to push is prose, and prose is what this repository keeps
    discovering was never a gate — the same lesson as completion tokens that could never
    match and a `--force` that bypasses everything at once.

    So the remote ref is read before and after every execution. If it moved, the node
    FAILS with the violation named, whatever the agent reported about itself.
    """
    from control.execution.workflow.autonomy import detect_push

    assert detect_push("abc1234", "abc1234") == ""

    created = detect_push("", "def5678")
    assert created, "creating the remote branch IS the push this forbids"
    assert "may not push" in created

    moved = detect_push("abc1234", "def5678")
    assert "abc1234"[:8] in moved and "def5678"[:8] in moved
    assert "may not push" in moved


def test_the_execution_boundary_is_stated_to_the_agent_as_well_as_checked():
    """Checking without telling would be a trap: the agent is given the rule AND the rule
    is verified. Neither alone is enough — an unstated rule is unfair, an unchecked one is
    decoration."""
    import inspect

    from control.execution.workflow.runner import WorkflowRunner

    src = inspect.getsource(WorkflowRunner._run_node)
    assert "EXECUTION BOUNDARY" in src
    assert "Do NOT push" in src
    assert (
        "detect_push" in src and "remote_head" in src
    ), "the boundary is stated but never verified"


def test_the_retry_budget_is_two_and_exhaustion_diagnoses():
    """OPERATOR RULING: the budget is 2, and on exhaustion the loop "should not move on,
    it should figure out the issue using the review agent ... and determine the fix".

    A third silent attempt and a shrug are both refusals to look. `_diagnose` is a SEPARATE
    invocation rather than another execution attempt, because the agent that could not make
    the check pass is the least likely to see why — the same reason independent review
    exists at close.
    """
    import inspect

    from control.execution.workflow.autonomy import RETRY_BUDGET
    from control.execution.workflow.runner import WorkflowRunner

    assert RETRY_BUDGET == 2, f"the operator set 2, found {RETRY_BUDGET}"

    src = inspect.getsource(WorkflowRunner._verify_with_retry)
    assert "RETRY_BUDGET" in src, "the budget is hardcoded somewhere else"
    assert "self._diagnose(" in src, "exhaustion moves on instead of diagnosing"

    diag = inspect.getsource(WorkflowRunner._diagnose)
    assert "fresh reviewer" in diag
    assert "work order" in diag, "the diagnosis must say whether this needs a work order"


def test_execution_is_opt_in():
    """It spawns an agent that edits the repository unattended. Making every existing
    `ds workflow run` do that silently would be reckless, so the default is unchanged."""
    import inspect

    from control.execution.workflow.runner import WorkflowRunner

    sig = inspect.signature(WorkflowRunner.__init__)
    assert sig.parameters["execute"].default is False

    r = WorkflowRunner.__new__(WorkflowRunner)
    r.dry_run = False
    r.execute = False
    # With execute off the wave must not reach the provider at all.
    wave = inspect.getsource(WorkflowRunner._execute_wave)
    assert (
        "if self.execute and success and not self.dry_run:" in wave
    ), "execution is not gated on the flag"


def test_the_operators_positions_are_rules_that_run_not_prose():
    """OPERATOR: "these should be rules for the operator not prose though."

    The first version was a paragraph handed to a model — which is exactly what its own
    second line forbids: an instruction someone is trusted to follow. Encoding
    GATES, NOT PROSE as prose is the sharpest version of the mistake this repository keeps
    making, and the operator caught it.

    Each position is now a predicate that runs against what actually happened in a node.
    The text handed to a reviewing agent is DERIVED from the rules, so it cannot drift the
    way a comment drifts from its code.
    """
    from control.execution.workflow.autonomy import (
        OPERATOR_RULES,
        RuleContext,
        evaluate_operator_rules,
        stance_brief,
    )

    assert len(OPERATOR_RULES) >= 6
    for rule in OPERATOR_RULES:
        assert callable(rule.check), f"{rule.rule_id} is a statement with no check"

    # Every rule fires on its own case — a rule that cannot fail is decoration.
    cases = {
        "no_false_done": RuleContext("n", {"completion_check": "x"}, True, "blocked", "why"),
        "gates_not_prose": RuleContext("n", {"completion_contains": "X"}, True, "completed"),
        "absence_is_not_clean": RuleContext("n", {}, True, "completed"),
        "never_force": RuleContext(
            "n", {"completion_check": "x"}, True, "completed", output="ds close --force"
        ),
        "never_push": RuleContext(
            "n", {"completion_check": "x"}, True, "completed", remote_after="ab12cd34"
        ),
    }
    for rule_id, ctx in cases.items():
        hits = " ".join(evaluate_operator_rules(ctx))
        assert rule_id in hits, f"{rule_id} did not fire on its own case: {hits}"

    # And stays silent on a clean node, or it is noise.
    clean = RuleContext("n", {"completion_check": "git status"}, True, "completed")
    assert evaluate_operator_rules(clean) == []

    brief = stance_brief()
    for rule in OPERATOR_RULES:
        assert rule.rule_id.upper() in brief, f"{rule.rule_id} is enforced but never stated"
        assert rule.statement in brief
    assert "PUSH BACK" in brief


def test_a_diagnosis_is_registered_not_just_reported():
    """EVERY DEFECT IS REGISTERED. A finding that lives only in this run's output is lost
    the moment the terminal scrolls — the operator's standing rule, and the reason
    GitHub-issue-only tracking was banned.

    Registration goes through create_task, the authoring door, so the record carries an
    event and survives a projection rebuild. Raw SQL would be deleted by the next rebuild,
    which is the whole reason that door exists.
    """
    import inspect

    from control.execution.workflow.autonomy import prescribe
    from control.execution.workflow.runner import WorkflowRunner

    assert "prescribe(" in inspect.getsource(
        WorkflowRunner._diagnose
    ), "a diagnosis is produced and then dropped"
    src = inspect.getsource(prescribe)
    assert "create_task" in src, "registration bypasses the authoring door"
    assert "work order" in src.lower()


def test_prescribing_never_breaks_the_run(tmp_path):
    """Bookkeeping must not be able to stop the work, the same rule the delivery-boundary
    stamps follow. A prescription that cannot be written degrades to a note."""
    from control.execution.workflow.autonomy import prescribe

    outcome = prescribe(
        "cause: the check names a file that does not exist",
        node_id="n1",
        reason="exited 1",
        source_root=tmp_path / "nowhere",
        dream_studio_home=tmp_path / "nowhere",
    )
    assert outcome.ok is True
    assert outcome.registered, "a failed registration must say so rather than vanish"
