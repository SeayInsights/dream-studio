"""WorkflowRunner — bridges workflow state management with skill invocation.

Reads current workflow state, computes ready nodes per dependency wave,
invokes each node's skill via direct imports of
``core.skills.invocation`` (A3 — replaced the legacy
``subprocess.run([sys.executable, '-m', 'interfaces.cli.ds', 'skill',
'invoke', specifier])`` self-shell-out so each node skips an
interpreter respawn).
"""

from __future__ import annotations

import sys
import subprocess
import time
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from core.config import paths  # noqa: E402
from control.execution.workflow.validate import parse_workflow  # noqa: E402
from control.execution.workflow.engine import (  # noqa: E402
    _compute_ready_nodes,
    _check_context_budget,
    _file_lock,
    resolve_templates,
)
from control.execution.workflow.state import (  # noqa: E402
    _write_checkpoint,
    SCHEMA_VERSION,
)

# ── Skill specifier resolution ────────────────────────────────────────────────

# Maps bare mode names to their owning pack. Fully-qualified names (containing
# ':') bypass this table entirely. Entries reflect packs.yaml modes as of Slice 9.
_BARE_TO_PACK: dict[str, str] = {
    # ds-core
    "think": "ds-core",
    "plan": "ds-core",
    "build": "ds-core",
    "review": "ds-core",
    "verify": "ds-core",
    "ship": "ds-core",
    "handoff": "ds-core",
    "recap": "ds-core",
    "explain": "ds-core",
    # ds-quality
    "debug": "ds-quality",
    "polish": "ds-quality",
    "harden": "ds-quality",
    "pr-security-scan": "ds-quality",
    "structure-audit": "ds-quality",
    "learn": "ds-quality",
    "coach": "ds-quality",
    "audit": "ds-quality",
    # ds-security
    "dast": "ds-security",
    "binary-scan": "ds-security",
    "mitigate": "ds-security",
    "comply": "ds-security",
    "netcompat": "ds-security",
    # ds-analyze
    "multi": "ds-analyze",
    "domain-re": "ds-analyze",
    "repo": "ds-analyze",
    "intelligence": "ds-analyze",
    # ds-domains
    "game-dev": "ds-domains",
    "saas-build": "ds-domains",
    "mcp-build": "ds-domains",
    "dashboard-dev": "ds-domains",
    "client-work": "ds-domains",
    "design": "ds-domains",
    # ds-project
    "scope": "ds-project",
    "resume": "ds-project",
    # ds-setup
    "wizard": "ds-setup",
    "jit": "ds-setup",
    # ds-workflow
    "workflow": "ds-workflow",
}

# ── Command node routing ──────────────────────────────────────────────────────

# Maps node `type:` field values to ds-core skill modes for command: nodes.
# Nodes with no type: field default to _DEFAULT_COMMAND_MODE.
_NODE_TYPE_TO_MODE: dict[str, str] = {
    "research": "think",
    "analysis": "think",
    "synthesis": "think",
    "report": "build",
    "config": "build",
    "plan": "plan",
}
_DEFAULT_COMMAND_MODE = "build"

# A completion check observes an effect that ALREADY happened -- a git ref, a
# status query, a gate's last line. It must be a cheap read, never the work itself.
_COMPLETION_CHECK_TIMEOUT = 60

# The operator set the retry budget; imported so there is one definition of it.
from control.execution.workflow.autonomy import RETRY_BUDGET  # noqa: E402


def resolve_specifier(skill_raw: str) -> str:
    """Resolve a raw skill field value to a fully-qualified ``pack:mode`` specifier.

    If the value already contains ``:``, return it unchanged.
    Otherwise look it up in the bare-mode table; fall back to ``ds-core:<skill_raw>``.
    """
    if ":" in skill_raw:
        return skill_raw
    pack = _BARE_TO_PACK.get(skill_raw, "ds-core")
    return f"{pack}:{skill_raw}"


def _load_full_yaml_nodes(yaml_path: str) -> dict[str, Any]:
    """Load full YAML content including block scalars via yaml.safe_load.

    Returns a node-id → node dict.  Falls back to {} on any parse error so
    the runner degrades gracefully rather than crashing.
    """
    try:
        import yaml as _yaml

        raw = _yaml.safe_load(Path(yaml_path).read_text(encoding="utf-8"))
        return {
            n["id"]: n for n in (raw or {}).get("nodes", []) if isinstance(n, dict) and "id" in n
        }
    except Exception:
        return {}


# ── WorkflowRunner ────────────────────────────────────────────────────────────


class WorkflowRunner:
    """Execute a workflow by iterating dependency waves until completion or failure.

    Args:
        wf_key: Workflow key (from ``workflow_state start`` output).
        dry_run: If True, log what would be invoked but never call any skill.
    """

    def __init__(self, wf_key: str, dry_run: bool = False, execute: bool = False) -> None:
        self.wf_key = wf_key
        self.dry_run = dry_run
        # EXECUTION IS OPT-IN. It spawns an agent that edits this repository unattended;
        # making every existing `ds workflow run` do that silently would be reckless.
        self.execute = execute
        # Why the last run() stopped, when it stopped at "blocked". Always present, so a
        # caller never has to guess whether the attribute exists before reading it.
        self.blocked_on: str = ""

    # ── Public API ────────────────────────────────────────────────────────

    def run(self) -> str:
        """Execute the workflow to completion (or until blocked/aborted).

        Returns the final workflow status string.
        """
        while True:
            state = self._load_state()
            wf = state.get("active_workflows", {}).get(self.wf_key)
            if wf is None:
                raise KeyError(f"Workflow '{self.wf_key}' not found in state")

            wf_status = wf.get("status", "running")
            if wf_status in ("completed", "completed_with_failures", "aborted", "paused"):
                return wf_status

            yaml_path = wf.get("yaml_path", "")
            if not yaml_path or not Path(yaml_path).is_file():
                print(f"[runner] ERROR: YAML not found at {yaml_path!r}", file=sys.stderr)
                return "aborted"

            yaml_data = parse_workflow(yaml_path)
            yaml_nodes: dict[str, Any] = {
                n["id"]: n for n in yaml_data.get("nodes", []) if "id" in n
            }
            full_yaml_nodes: dict[str, Any] = _load_full_yaml_nodes(yaml_path)
            state_nodes: dict[str, Any] = wf.get("nodes", {})

            ready, skipped = _compute_ready_nodes(yaml_nodes, state_nodes, wf)

            if skipped:
                self._mark_skipped(skipped, reason="condition false")
                state = self._load_state()
                wf = state.get("active_workflows", {}).get(self.wf_key, {})
                state_nodes = wf.get("nodes", {})

            if not ready:
                running = [nid for nid, n in state_nodes.items() if n.get("status") == "running"]
                if running:
                    # Agents still in flight; caller should poll or wait
                    return "running"
                # Nothing ready and nothing running — blocked or done
                all_statuses = {n.get("status") for n in state_nodes.values()}
                if all_statuses <= {"completed", "skipped"}:
                    return "completed"
                # A run that reached the end without observing some of its nodes did not
                # complete -- it finished. Reporting "completed" here would restore the
                # exact claim this work order exists to stop, one level up from the node.
                if all_statuses <= {"completed", "skipped", "unverified"}:
                    self.blocked_on = self._describe_unverified(state_nodes)
                    return "completed_with_unverified"
                if all_statuses <= {"completed", "skipped", "failed", "unverified"}:
                    return "completed_with_failures"
                self.blocked_on = self._describe_blockage(state_nodes)
                return "blocked"

            # Context budget guard for parallel waves
            if len(ready) > 1 and not self.dry_run:
                budget = _check_context_budget(len(ready))
                if budget == "block":
                    self._mark_skipped(
                        ready, reason="context budget too high for parallel dispatch"
                    )
                    continue

            wave_failed = self._execute_wave(ready, yaml_nodes, yaml_data, full_yaml_nodes)
            if wave_failed:
                # Propagate — state already updated; loop will detect blocked state
                continue

        # unreachable; loop exits via return statements above

    def advance(self) -> list[str]:
        """Execute one wave of ready nodes and return their node IDs.

        Unlike ``run()``, does not loop — useful for step-by-step execution.
        Returns empty list if blocked or finished.
        """
        state = self._load_state()
        wf = state.get("active_workflows", {}).get(self.wf_key)
        if wf is None:
            return []

        if wf.get("status") in ("completed", "completed_with_failures", "aborted", "paused"):
            return []

        yaml_path = wf.get("yaml_path", "")
        if not yaml_path or not Path(yaml_path).is_file():
            return []

        yaml_data = parse_workflow(yaml_path)
        yaml_nodes: dict[str, Any] = {n["id"]: n for n in yaml_data.get("nodes", []) if "id" in n}
        full_yaml_nodes: dict[str, Any] = _load_full_yaml_nodes(yaml_path)
        state_nodes: dict[str, Any] = wf.get("nodes", {})

        ready, skipped = _compute_ready_nodes(yaml_nodes, state_nodes, wf)
        if skipped:
            self._mark_skipped(skipped, reason="condition false")
        if not ready:
            return []

        self._execute_wave(ready, yaml_nodes, yaml_data, full_yaml_nodes)
        return ready

    # ── Internal helpers ──────────────────────────────────────────────────

    def _load_state(self) -> dict:
        p = paths.state_dir() / "workflows.json"
        if not p.is_file():
            return {"schema_version": SCHEMA_VERSION, "active_workflows": {}}
        try:
            import json

            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {"schema_version": SCHEMA_VERSION, "active_workflows": {}}

    def _execute_wave(
        self,
        node_ids: list[str],
        yaml_nodes: dict[str, Any],
        yaml_data: dict,
        full_yaml_nodes: dict[str, Any] | None = None,
    ) -> bool:
        """Execute all nodes in ``node_ids`` sequentially (parallel in a future wave).

        Returns True if any node failed.
        """

        wf_state = self._load_state()
        wf = wf_state.get("active_workflows", {}).get(self.wf_key, {})
        session_dir = wf.get("session_dir")

        any_failed = False
        for node_id in node_ids:
            ynode = yaml_nodes[node_id]
            skill_raw = ynode.get("skill", "")

            # Template resolution (e.g. {{params.audit}})
            skill_raw = resolve_templates(skill_raw, wf, session_dir)

            is_command_node = False
            if not skill_raw:
                # No skill: field — check for command: field (LLM instruction prompt)
                has_command = bool(ynode.get("command"))
                if not has_command:
                    print(
                        f"[runner] Node {node_id}: no skill or command defined — skipping",
                        flush=True,
                    )
                    self._update_node(node_id, "skipped", "no skill or command defined")
                    self._emit_node_event(node_id, "skipped")
                    continue

                # Route command: node through the appropriate core skill mode
                node_type = str(ynode.get("type", "") or "")
                mode = _NODE_TYPE_TO_MODE.get(node_type, _DEFAULT_COMMAND_MODE)
                specifier = resolve_specifier(mode)
                is_command_node = True

                # Resolve actual command content from full YAML (block scalar)
                full_ynode = (full_yaml_nodes or {}).get(node_id, {})
                raw_command = full_ynode.get("command", "") or ""
                if raw_command and not isinstance(raw_command, bool):
                    resolved_command = resolve_templates(raw_command, wf, session_dir)
                else:
                    resolved_command = (
                        f"# Workflow node: {node_id}\n# (command content unavailable)\n"
                    )
                context_path = self._write_command_context(
                    node_id, resolved_command, node_type, yaml_data
                )
                print(
                    f"[runner] Node {node_id}: executing command via {specifier}"
                    f" — prompt at {context_path}",
                    flush=True,
                )
            else:
                specifier = resolve_specifier(skill_raw)
                print(f"[runner] Node {node_id}: invoking {specifier}", flush=True)

            self._update_node(node_id, "running", None)

            t0 = time.monotonic()
            success, output = self._invoke_skill(specifier, node_id)

            # RUN IT, do not merely deliver it. Without this, the node whose job is to
            # implement the tasks cannot satisfy a check asking whether the tasks are
            # implemented -- measured: the loop halted at implement-tasks reporting "15
            # task(s) still pending", which is the work, not an obstacle.
            _node_yaml_exec = (full_yaml_nodes or {}).get(node_id) or ynode
            if self.execute and success and not self.dry_run:
                success, output = self._run_node(node_id, _node_yaml_exec, output)
            duration = round(time.monotonic() - t0, 2)

            # THE COMPLETION DECISION DOES NOT LOOK AT THIS TEXT AT ALL, which is why
            # the synthetic summary is harmless here. A previous cut threaded the real
            # output into _verify_completion to stop it checking this receipt; a later
            # review pointed out the method had by then stopped reading the parameter
            # entirely, so the thread was ceremony. The only evidence available to this
            # runner is a completion_check subprocess observing state from outside.
            if is_command_node and success:
                output = f"{node_id} executed via {specifier}"

            if not success:
                status, reason = "failed", None
            elif self.execute and not self.dry_run:
                status, reason = self._verify_with_retry(node_id, _node_yaml_exec, output)
            else:
                # Read the FULL yaml node, not the parsed summary: completion_check
                # is a block scalar and lives only in the full node. Resolved here
                # rather than reusing `full_ynode`, which is assigned only inside the
                # command-node branch -- referencing it for a skill node raised
                # UnboundLocalError and broke four existing tests.
                _node_yaml = (full_yaml_nodes or {}).get(node_id) or ynode
                status, reason = self._verify_completion(node_id, _node_yaml)
            if reason:
                output = f"{output}\n\n[completion] {status.upper()}: {reason}"
            self._update_node(node_id, status, output, duration=duration)
            self._emit_node_event(node_id, status)
            self._emit_progress_event(wf_state)

            if not success:
                any_failed = True
                print(f"[runner] Node {node_id} FAILED (duration={duration}s)", flush=True)

        return any_failed

    def _invoke_skill(self, specifier: str, node_id: str) -> tuple[bool, str]:
        """Invoke a skill via direct imports of ``core.skills.invocation``.

        Returns ``(success, output)`` where ``output`` is the same
        operator-style text the legacy subprocess CLI handler produced
        (SKILL.md content + footer with specifier/mode/target). Truncated
        to 2000 chars to match the pre-A3 contract.

        dry_run always returns (True, "[dry_run]") without loading the
        skill or emitting any spool event.
        """

        if self.dry_run:
            print(
                f"[runner] [dry_run] would invoke: {specifier} (node={node_id})",
                flush=True,
            )
            return True, "[dry_run]"

        try:
            from core.skills.invocation import load_skill_content, record_skill_invocation

            source_root = Path(__file__).resolve().parents[3]

            load_result = load_skill_content(specifier=specifier, source_root=source_root)
            if not load_result.get("ok"):
                return False, str(load_result.get("error", "skill load failed"))[:2000]

            # Best-effort spool emission of ``skill.invoked``. Failure
            # inside record_skill_invocation is already swallowed there,
            # but wrap defensively so any import-time exception (e.g.
            # spool root unreachable) doesn't break the node.
            try:
                record_skill_invocation(
                    specifier=specifier,
                    target=None,
                    work_order_id=None,
                    project_id=None,
                    source_root=source_root,
                )
            except Exception:
                pass

            # Reproduce the legacy CLI handler's stdout block so workflow
            # state captures the same operator-facing text.
            footer_lines = [
                "---",
                f"Skill: {specifier}",
                "Mode: direct",
                "Target: not specified",
                "Work order: none",
                "Invocation recorded.",
                "",
                (
                    "The AI reading this output has the skill instructions above "
                    "and should now execute them."
                ),
            ]
            output = (
                load_result["skill_content"].rstrip() + "\n" + "\n".join(footer_lines)
            ).strip()
            return True, output[:2000]
        except Exception as exc:
            return False, str(exc)[:500]

    # WO-NODE-COMPLETION-EVIDENCE: a node is complete when its effect is OBSERVABLE.
    #
    # Operator: "I'm tired of having to update you to move on ... register everything that
    # is needed and an orchestrator continues on making sure everything moves along
    # correctly."
    #
    # The orchestrator already exists -- execute-work-orders.yaml has 14 nodes covering the
    # whole loop, and this runner computes ready nodes from real dependency logic. What was
    # missing is not a driver. It is that completion was UNVERIFIED: _invoke_skill loads a
    # node's text, returns it with the footer "The AI reading this output has the skill
    # instructions above and should now execute them", and the wave then marked the node
    # "completed" on a successful LOAD. All 14 nodes are prose-for-an-agent; none is
    # executable as written.
    #
    # So a driver over this would march through fourteen nodes printing prompts and
    # declaring success with no work done -- the assert-instead-of-verify defect at the
    # orchestration layer, where it is hardest to notice. That is why the driver is
    # sequenced AFTER this.
    #
    # A node may declare `completion_check`: a shell command whose exit status is the
    # evidence. Optionally `completion_contains` requires text in its output, for the case
    # where a command succeeds but says the wrong thing (a gate that prints
    # "Overall: FAIL" and exits 0).

    def _describe_unverified(self, state_nodes: dict) -> str:
        """Which nodes finished without anyone observing their effect."""
        lines = [
            f"  {nid}: no completion_check, so nothing confirmed this node's effect"
            for nid, node in state_nodes.items()
            if node.get("status") == "unverified"
        ]
        return chr(10).join(lines)

    def _run_node(self, node_id: str, ynode: dict, prompt: str) -> tuple[bool, str]:
        """Execute the node's prompt through the configured provider. Never pushes.

        Reuses ``core.adapters.grader_runner.run_generation`` -- the same provider-neutral
        spawn the verify plane uses -- so which agent EXECUTES a node follows the same
        profile resolution as which agent GRADES one.

        THE NO-PUSH RULE IS MEASURED, NOT ASKED. The remote ref is read before and after;
        if it moved, the node fails with the violation named. Telling an agent not to push
        is prose, and prose is what this repository keeps finding was never a gate.
        """
        from control.execution.workflow.autonomy import detect_push, remote_head

        repo_root = Path(__file__).resolve().parents[3]
        before = remote_head(repo_root)
        timeout = int(ynode.get("timeout_seconds") or 600)

        guarded = (
            f"{prompt}\n\n"
            "--- EXECUTION BOUNDARY ---\n"
            "Edit the working tree. Do NOT push, and do NOT merge. Opening a pull request "
            "is the reviewing step's decision, not yours. This boundary is checked after "
            "you finish, not taken on trust.\n"
        )
        try:
            from core.adapters.grader_runner import run_generation

            proc = run_generation(guarded, timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - a provider fault is a node failure
            return False, f"provider could not be invoked ({type(exc).__name__}): {exc}"

        after = remote_head(repo_root)
        violation = detect_push(before, after)
        if violation:
            return False, f"EXECUTION BOUNDARY VIOLATED: {violation}"

        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        if proc.returncode != 0:
            return False, f"provider exited {proc.returncode}: {out[-400:]}"
        return True, out

    def _verify_with_retry(self, node_id: str, ynode: dict, output: str) -> tuple[str, str | None]:
        """Verify; retry twice while merely not-there-yet; then DIAGNOSE rather than move on.

        Operator ruling: the budget is 2, and on exhaustion the loop "should not move on,
        it should figure out the issue using the review agent ... and determine the fix".
        A third silent attempt and a shrug are both refusals to look.
        """
        from control.execution.workflow.autonomy import RETRY_BUDGET

        status, reason = self._verify_completion(node_id, ynode)
        attempt = 0
        while status == "blocked" and attempt < RETRY_BUDGET:
            attempt += 1
            print(
                f"[runner] Node {node_id}: blocked, retrying ({attempt}/{RETRY_BUDGET}) — {reason}",
                flush=True,
            )
            ok, out = self._run_node(node_id, ynode, output)
            if not ok:
                return "failed", out
            status, reason = self._verify_completion(node_id, ynode)

        if status == "blocked":
            diagnosis = self._diagnose(node_id, ynode, reason or "")
            reason = f"{reason} | after {attempt} attempt(s), diagnosis: {diagnosis}"
        return status, reason

    def _diagnose(self, node_id: str, ynode: dict, reason: str) -> str:
        """Ask a fresh reviewer WHY the node will not complete, and what would fix it.

        Deliberately a separate invocation rather than another execution attempt: the
        agent that could not make the check pass is the least likely to see why. A clean
        reader is the point, the same reason independent review exists at close.
        """
        from control.execution.workflow.autonomy import stance_brief
        from core.work_orders.scenario_taxonomy import SCENARIO_TAXONOMY

        check = str(ynode.get("completion_check") or "(none declared)")
        prompt = (
            f"{stance_brief()}\n\n"
            f"A workflow node did not complete after {RETRY_BUDGET} attempts.\n\n"
            f"Node: {node_id}\n"
            f"Its completion check: {check}\n"
            f"What the check reported: {reason}\n\n"
            "You are a fresh reviewer. Do not assume the node's prompt was wrong or right.\n\n"
            "STEP THROUGH THIS TAXONOMY rather than improvising a checklist. A reviewer who\n"
            "improvises covers what occurs to them; one that walks a fixed list also covers\n"
            "the classes that do not. Skip a class only when it genuinely cannot apply.\n\n"
            f"{SCENARIO_TAXONOMY}\n\n"
            "State, in at most six lines:\n"
            "  1. The most likely CAUSE, named specifically.\n"
            "  2. The concrete FIX, as an action someone can take.\n"
            "  3. Whether this is one task or several (several means it needs a work order).\n"
        )
        try:
            from core.adapters.grader_runner import run_generation

            proc = run_generation(prompt, timeout=180)
        except Exception as exc:  # noqa: BLE001 - a diagnosis must never break the run
            return f"diagnosis unavailable ({type(exc).__name__}: {exc})"
        if proc.returncode != 0:
            return f"diagnosis unavailable (provider exited {proc.returncode})"
        diagnosis = ((proc.stdout or "").strip() or "diagnosis was empty")[:1200]

        # PRESCRIBE, do not merely observe. A finding that lives only in this run's output
        # is lost the moment the terminal scrolls -- the operator's standing rule is that
        # every defect is registered in the authority. One finding becomes a task; several
        # become a work order, because a work order carrying one task is mis-sized.
        try:
            from control.execution.workflow.autonomy import prescribe

            outcome = prescribe(
                diagnosis,
                node_id=node_id,
                reason=reason,
                source_root=Path(__file__).resolve().parents[3],
            )
            if outcome.registered:
                diagnosis += " | registered: " + "; ".join(outcome.registered)
        except Exception as exc:  # noqa: BLE001 - prescribing must never break the run
            diagnosis += f" | could not register ({type(exc).__name__})"
        return diagnosis

    def _describe_blockage(self, state_nodes: dict) -> str:
        """Why the run stopped, in terms an operator can act on.

        `run()` returned the bare string "blocked" and `ds workflow run` printed
        "[workflow] final status: blocked". That is a status, not direction -- it names
        no node, no reason, and nothing to do, so the loop hands back exactly the
        question the operator started with. A driver that stops without saying what it
        is waiting on has not removed the human from the loop; it has moved them to a
        worse position, because now they must reconstruct the state themselves.
        """
        lines: list[str] = []
        for nid, node in state_nodes.items():
            status = node.get("status")
            if status in ("completed", "skipped", "pending"):
                continue
            reason = (node.get("blocked_reason") or "").strip()
            if not reason:
                out = (node.get("output") or "").strip()
                marker = "[completion] "
                if marker in out:
                    reason = out.split(marker, 1)[1].splitlines()[0]
            lines.append(f"  {nid}: {status}" + (f" — {reason}" if reason else ""))
        if not lines:
            return "no node reports a blocking status; check for a dependency cycle"
        return chr(10).join(lines)

    def _verify_completion(self, node_id: str, ynode: dict) -> tuple[str, str | None]:
        """Return ``(status, reason)`` for a node whose prompt was delivered.

        Two kinds of evidence, because the nodes come in two kinds.

        ``completion_contains`` ALONE checks the node's OWN output. Every node in
        execute-work-orders ends by telling the agent to print a specific token --
        "Print: GATES: PASS", "Print: BRANCH: <name>", "Print: REVIEW_PASS" -- so the
        token is already the declared observable, and the agent either produced it or did
        not. Requiring a subprocess to confirm that would mean inventing an external
        effect for a node whose effect is a report.

        ``completion_check`` runs a shell command whose exit status is the evidence, for
        nodes with an effect worth confirming independently of what the agent claims --
        a branch that exists, a work order the authority says is closed.
        ``completion_contains`` then applies to THAT command's output.

        * neither declared -> ``("unverified", why)``. NOT "completed": a node whose
          effect nobody looked at has not been shown to have happened, and reporting it as
          done is the exact claim this work order exists to stop.
        * evidence holds -> ``("completed", None)``
        * evidence absent -> ``("blocked", what was expected and what was seen)``

        BLOCKED IS NOT FAILED. Failed means the work was attempted and went wrong; blocked
        means the effect is not there yet, which for a prose node usually means the agent
        has not done it. A driver must stop at blocked without recording a failure.
        """
        # DRY RUN SIMULATES; it does not execute. Nothing ran, so no completion condition
        # can hold, and verifying one would make every dry run report blocked -- turning a
        # planning tool into a wall. The simulation keeps its old meaning: this node WOULD
        # complete.
        if self.dry_run:
            return "completed", None

        check = (ynode.get("completion_check") or "").strip()
        expected_raw = (ynode.get("completion_contains") or "").strip()
        # A check that cannot name the thing it is checking can only assert generalities.
        # `{{node.output}}` and `{{node.field}}` resolve here exactly as they do in a
        # node's prompt -- without this, "does the PR exist" could not reference the PR
        # number the previous node printed, and every check would have to be repo-global.
        if "{{" in check or "{{" in expected_raw:
            try:
                from control.execution.workflow.engine import resolve_templates

                wf = (self._load_state().get("active_workflows", {}) or {}).get(self.wf_key, {})
                check = resolve_templates(check, wf).strip()
                expected_raw = resolve_templates(expected_raw, wf).strip()
            except Exception:
                # An unresolvable template leaves the literal in place; the check then
                # fails and the node blocks with the reason, which is the right outcome.
                pass
        if not check:
            # WHY completion_contains ALONE IS NOT ENOUGH, corrected after an independent
            # review. I had it check "the node's own output", reasoning that each node
            # ends by telling the agent to print a token. The runner has no such output:
            # _invoke_skill LOADS a skill and returns its SKILL.md text plus a footer, and
            # the agent that would produce a report reads that text out of band. There is
            # no execution result here to inspect. Checking the loaded prompt instead would
            # be worse than useless -- every token appears in its own prompt by
            # construction, so every node would "complete" by reading its own instructions.
            hint = (
                " (completion_contains alone cannot be checked here: this runner delivers a"
                " prompt and never sees what the agent then does. Pair it with a"
                " completion_check that observes the effect -- a git ref, an authority"
                " query -- or leave the node honestly unverified.)"
                if expected_raw
                else ""
            )
            return (
                "unverified",
                "no completion_check declared, so the effect of this node was never "
                "observed -- its prompt was delivered and nothing confirms the work" + hint,
            )

        try:
            proc = subprocess.run(
                check,
                shell=True,
                cwd=str(Path(__file__).resolve().parents[3]),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_COMPLETION_CHECK_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return (
                "blocked",
                f"completion_check timed out after {_COMPLETION_CHECK_TIMEOUT}s: {check}",
            )
        except OSError as exc:
            return "blocked", f"completion_check could not run ({type(exc).__name__}): {check}"

        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        if proc.returncode != 0:
            tail = out.splitlines()[-1][:160] if out else "(no output)"
            return (
                "blocked",
                f"completion_check exited {proc.returncode}: {check} -> {tail}",
            )

        expected = expected_raw
        if expected and expected not in out:
            return (
                "blocked",
                f"completion_check succeeded but its output does not contain "
                f"{expected!r}: {check}",
            )
        return "completed", None

    def _update_node(
        self,
        node_id: str,
        status: str,
        output: str | None,
        duration: float | None = None,
    ) -> None:
        """Atomically update a node's status in workflows.json."""
        import json

        now = datetime.now(UTC).isoformat()
        lock_path = paths.state_dir() / "workflows.json.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        with _file_lock(lock_path):
            p = paths.state_dir() / "workflows.json"
            if not p.is_file():
                return
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return

            wf = data.get("active_workflows", {}).get(self.wf_key)
            if wf is None:
                return

            node = wf.setdefault("nodes", {}).setdefault(node_id, {})
            node["status"] = status

            if status == "running" and "started" not in node:
                node["started"] = now
            if status in ("completed", "failed", "skipped"):
                node["finished"] = now
            if status == "completed":
                completed = wf.setdefault("completed_nodes", [])
                if node_id not in completed:
                    completed.append(node_id)
            if output is not None:
                node["output"] = output
            if duration is not None:
                node["duration_s"] = duration

            wf["current_node"] = node_id

            # Update workflow-level status
            statuses = [n.get("status") for n in wf.get("nodes", {}).values()]
            if all(s in ("completed", "skipped") for s in statuses):
                wf["status"] = "completed"
            elif all(s in ("completed", "skipped", "failed") for s in statuses):
                wf["status"] = "completed_with_failures"

            p.write_text(json.dumps(data, indent=2), encoding="utf-8")

        _write_checkpoint(self.wf_key, node_id, status)

    def _mark_skipped(self, node_ids: list[str], reason: str) -> None:
        for nid in node_ids:
            self._update_node(nid, "skipped", f"SKIPPED: {reason}")

    def _emit_node_event(self, node_id: str, status: str) -> None:
        """Emit a workflow.node.completed event to the spool."""
        try:
            from spool.writer import write_event
            from canonical.events.types import EventType

            write_event(
                {
                    "event_type": EventType.WORKFLOW_NODE_COMPLETED.value,
                    "workflow_key": self.wf_key,
                    "node_id": node_id,
                    "status": status,
                    "dry_run": self.dry_run,
                }
            )
        except Exception:
            pass

    def _write_command_context(
        self,
        node_id: str,
        command: str,
        node_type: str,
        yaml_data: dict,
    ) -> Path:
        """Write command: node prompt to .planning/workflow/<wf_key>/<node_id>-prompt.md.

        The file gives Claude the node-specific instructions.  The skill
        invocation (ds-core:build / think / plan) provides the execution
        framework; this file provides the task payload.
        """
        try:
            base = paths.plugin_root()
        except (RuntimeError, Exception):
            base = Path(__file__).resolve().parents[3]
        context_dir = base / ".planning" / "workflow" / self.wf_key
        context_dir.mkdir(parents=True, exist_ok=True)
        wf_name = str(yaml_data.get("name", "") or "unknown")
        context_file = context_dir / f"{node_id}-prompt.md"
        content = (
            f"# Workflow Node: {node_id}\n"
            f"# Workflow: {wf_name}\n"
            f"# Node type: {node_type or 'unspecified'}\n\n"
            f"{command}"
        )
        context_file.write_text(content, encoding="utf-8")
        return context_file

    def _emit_progress_event(self, state: dict) -> None:
        """Emit a workflow.progress.updated event after each node completes."""
        try:
            from spool.writer import write_event
            from canonical.events.types import EventType

            wf = state.get("active_workflows", {}).get(self.wf_key, {})
            nodes = wf.get("nodes", {})
            done = sum(1 for n in nodes.values() if n.get("status") in ("completed", "skipped"))
            total = len(nodes)

            write_event(
                {
                    "event_type": EventType.WORKFLOW_PROGRESS_UPDATED.value,
                    "workflow_key": self.wf_key,
                    "workflow_name": wf.get("workflow", ""),
                    "done": done,
                    "total": total,
                    "dry_run": self.dry_run,
                }
            )
        except Exception:
            pass
