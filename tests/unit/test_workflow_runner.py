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
    assert "Invocation recorded; no work was performed by the runner." in output

    # WO 66069823: the output must say WHAT IT IS before it says anything else.
    #
    # `success is True` above means the skill LOADED, not that anything ran -- and the
    # recorded output used to open with the SKILL.md body, so a workflow status dump
    # showed what looked like a result. An operator read a stalled run as a broken
    # orchestrator when it was correctly waiting for a reader that `ds workflow run` does
    # not provide. The disclaimer leads, and leads for every skill node.
    assert output.startswith("[handoff] NOT EXECUTED"), (
        "the handoff disclaimer must come FIRST; below the instructions it is 2000 "
        f"characters from where a reader starts. Output began: {output[:80]!r}"
    )
    assert output.index("[handoff]") < output.index(
        "PLAN BODY"
    ), "the instructions must not precede the statement of what they are"


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


# -- WO 66069823: a dispatched node is not an executed one --------------------


def test_a_skill_node_that_executed_nothing_is_not_a_success(tmp_path):
    """`success` from _invoke_skill means LOADED, and the output must not imply more.

    THE REPORT THIS COMES FROM. An operator asked why the orchestrator was not working.
    Workflow `orch-verify` sat at 1/14 with three nodes `unverified` and one `blocked`,
    and the recorded output of its `implement-tasks` node began with the SKILL.md
    frontmatter -- `dream_studio: skill_id: ds-core, pack: core, mode: b`. That is the
    file, not a result.

    The runner was behaving correctly: it loads a skill's instructions, records the
    invocation, and leaves the work to an agent reading the output. Under
    `ds workflow run` there is no such reader, so the node correctly never completes. What
    was wrong is that nothing SAID so where anyone would look, and a faithful wait was
    indistinguishable from a failure.
    """
    from unittest.mock import MagicMock, patch

    runner = WorkflowRunner("wf-test", dry_run=False)
    fake_load = MagicMock(
        return_value={"ok": True, "skill_content": "---\nfrontmatter: yes\n---\nBODY"}
    )
    with (
        patch("core.skills.invocation.load_skill_content", fake_load),
        patch("core.skills.invocation.record_skill_invocation", MagicMock()),
    ):
        success, output = runner._invoke_skill("core:build", "implement-tasks")

    assert success is True, "loading succeeded; that is what this boolean means"
    assert not output.startswith("---"), (
        "the output still opens with skill frontmatter, which is what made a dispatched "
        "node read as an executed one"
    )
    for phrase in ("NOT EXECUTED", "DISPATCHED, not run", "no model"):
        assert phrase in output, f"the handoff statement omits {phrase!r}: {output[:160]!r}"


def test_the_handoff_statement_survives_the_output_budget():
    """Truncation must never remove the sentence that explains the rest.

    The output is capped so a huge SKILL.md cannot flood workflow state. A budget applied
    before the header would cut exactly the part a reader needs -- restoring the confusion
    this change removes, and doing it only for the largest skills, which are the ones
    least likely to be read closely.
    """
    from unittest.mock import MagicMock, patch

    runner = WorkflowRunner("wf-test", dry_run=False)
    fake_load = MagicMock(return_value={"ok": True, "skill_content": "X" * 50_000})
    with (
        patch("core.skills.invocation.load_skill_content", fake_load),
        patch("core.skills.invocation.record_skill_invocation", MagicMock()),
    ):
        _, output = runner._invoke_skill("core:build", "n1")

    assert output.startswith(
        "[handoff] NOT EXECUTED"
    ), "a 50k skill body pushed the disclaimer out of the recorded output"
    assert len(output) < 60_000, "the budget stopped applying entirely"


def test_every_progress_count_agrees_on_what_done_means():
    """Every site computing `done` must agree, and the guard must FIND them.

    The task that opened this was WRONG -- it assumed the count included `unverified`
    nodes, and all sites already excluded them, so `1/14` was accurate. What the check
    surfaced is that the same question is answered in several places, which is the shape
    that goes wrong quietly.

    THE FIRST VERSION NAMED THREE FILES AND A COUNT BY HAND. Its own review said so: a
    guard that lists its sources holds the invariant for the sources someone remembered,
    and the telemetry site writing `nodes_done` into a permanent event was outside the
    list. This one discovers every done-computation under control/execution/workflow/ and
    fails if any disagrees, so a fourth site added tomorrow is covered without an edit.
    """
    import re

    root = Path(__file__).resolve().parents[2] / "control" / "execution" / "workflow"
    assert root.is_dir(), root

    # ANCHORED ON THE DONE-COUNT ASSIGNMENT, not on any membership test mentioning
    # "completed". A broader pattern caught six distinct sets and failed, correctly: this
    # tree also asks "is this node finished" (completed|failed|skipped) and "is it
    # settled" (completed|unverified), which are different questions with different right
    # answers. Only the count reported as progress is claimed to be one question.
    pattern = re.compile(r"done\s*=\s*sum\(.*?\bin\s+\(([^)]*)\)", re.S)
    found: list[tuple[str, frozenset[str]]] = []
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            statuses = frozenset(
                x.strip().strip('"').strip("'") for x in match.group(1).split(",") if x.strip()
            )
            found.append((path.name, statuses))

    assert len(found) >= 4, (
        f"the finder located only {len(found)} done-computations under {root.name}/, so a "
        "clean result would mean it looked almost nowhere"
    )

    distinct = {statuses for _, statuses in found}
    assert len(distinct) == 1, (
        "the sites disagree about what counts as done, so one will be updated without the "
        f"others: {[(n, sorted(s)) for n, s in found]}"
    )

    only = next(iter(distinct))
    assert "unverified" not in only, (
        "a node whose completion nobody established counts as done, which is the "
        "compared-nothing-reported-clean shape"
    )


def test_a_dispatched_node_is_distinguishable_without_reading_its_text():
    """A caller that never reads prose must still be able to tell the two apart.

    The dispatch output was made to open with NOT EXECUTED, and this work order's own
    review pointed out that _invoke_skill still returns True and the wave still advances
    -- so to a gate, a status command, or any programmatic reader, a dispatched node
    looked exactly like an executed one. A fact carried only in text is unavailable to
    every consumer except a human.

    The node record now carries `executed`. Asserted on _update_node's contract rather
    than on a full workflow run, because the claim is that the field reaches the record.
    """
    import inspect

    src = inspect.getsource(WorkflowRunner._update_node)
    assert "executed" in inspect.signature(WorkflowRunner._update_node).parameters, (
        "_update_node cannot record whether the work was performed, so the distinction "
        "exists only in the output text"
    )
    assert 'node["executed"] = executed' in src, (
        "the parameter is accepted and never written to the node, which is a signature "
        "that looks like a fact and stores nothing"
    )

    caller = inspect.getsource(WorkflowRunner._execute_wave)
    assert "executed=bool(is_command_node)" in caller, (
        "the wave does not tell _update_node which kind of node this was, so every node "
        "records the same value and the field says nothing"
    )


def test_an_unverified_skill_node_still_releases_the_next_wave():
    """The behaviour the corrected decision record describes, pinned.

    An earlier draft of that record claimed a headless run stalls at the first skill node
    carrying a completion_check. It does not: `any_failed` is set only when `not success`,
    and an unverified node is a success as far as the wave is concerned, so the wave
    completes and the run advances -- halting later at a dependent node. orch-verify
    reached a blocked implement-tasks with three unverified nodes BEHIND it, which is what
    that distinction looks like in practice.

    Held on the engine rather than on the prose, so the record cannot drift back.
    """
    import inspect

    src = inspect.getsource(WorkflowRunner._execute_wave)

    assert (
        "if not success:" in src and "any_failed = True" in src
    ), "the wave-failure condition changed shape; this test pins what it is"
    # The failure flag must not be set for a non-success STATUS -- only for a failed call.
    begin = src.index("if not success:")
    failure_block = src[begin:]
    stop = failure_block.index("return any_failed")
    failure_block = failure_block[:stop]
    assert "unverified" not in failure_block, (
        "an unverified node now sets any_failed, which means the wave stops at the "
        "dispatch point -- the decision record in runner.py says it does not, and one of "
        "the two is now wrong"
    )


def test_the_done_count_guard_discovers_its_own_sources():
    """The guard must find the done-counts, not be told where they are.

    Its first version named three files and a transcribed count, and the telemetry site
    writing nodes_done into a permanent event was outside that list -- so the invariant it
    claimed for every progress count was held for most of them.

    This asserts the guard's own construction: that it walks the tree and anchors on the
    assignment, which is what makes a fourth site free.
    """
    import inspect

    src = inspect.getsource(test_every_progress_count_agrees_on_what_done_means)

    assert "rglob" in src, (
        "the done-count guard reads a fixed file list again, so a site added tomorrow is "
        "outside the invariant it claims to hold"
    )
    assert "done" in src and "sum" in src, "the guard no longer anchors on the assignment"
    for hardcoded in ('state_commands.py"', 'tracking.py"', 'runner.py"'):
        assert hardcoded not in src, (
            f"the guard names {hardcoded} explicitly, which is the transcription its own "
            "review refused"
        )
