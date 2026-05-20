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
import time
from datetime import datetime, timezone
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
    _read_state,
    _write_state,
    _state_lock,
    _write_checkpoint,
    SCHEMA_VERSION,
)

# ── Skill specifier resolution ────────────────────────────────────────────────

# Maps bare mode names to their owning pack. Fully-qualified names (containing
# ':') bypass this table entirely. Entries reflect packs.yaml modes as of Slice 9.
_BARE_TO_PACK: dict[str, str] = {
    # core (packs.yaml key: core)
    "think": "core",
    "plan": "core",
    "build": "core",
    "review": "core",
    "verify": "core",
    "ship": "core",
    "handoff": "core",
    "recap": "core",
    "explain": "core",
    # quality (packs.yaml key: quality)
    "debug": "quality",
    "polish": "quality",
    "harden": "quality",
    "pr-security-scan": "quality",
    "structure-audit": "quality",
    "learn": "quality",
    "coach": "quality",
    "audit": "quality",
    # security (packs.yaml key: security, non-ambiguous modes only)
    "dast": "security",
    "binary-scan": "security",
    "mitigate": "security",
    "comply": "security",
    "netcompat": "security",
    # analyze (packs.yaml key: analyze)
    "multi": "analyze",
    "domain-re": "analyze",
    "repo": "analyze",
    "intelligence": "analyze",
    # domains (packs.yaml key: domains)
    "game-dev": "domains",
    "saas-build": "domains",
    "mcp-build": "domains",
    "dashboard-dev": "domains",
    "client-work": "domains",
    "design": "domains",
    # career (packs.yaml key: career)
    "evaluate": "career",
    "apply": "career",
    "track": "career",
    "pdf": "career",
    # ds-project (packs.yaml key: ds-project — kept as-is)
    "scope": "ds-project",
    "resume": "ds-project",
    # setup (packs.yaml key: setup)
    "wizard": "setup",
    "jit": "setup",
    # meta/workflow (packs.yaml key: meta, skill: workflow)
    "workflow": "meta",
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


def resolve_specifier(skill_raw: str) -> str:
    """Resolve a raw skill field value to a fully-qualified ``pack:mode`` specifier.

    If the value already contains ``:``, return it unchanged.
    Otherwise look it up in the bare-mode table; fall back to ``ds-core:<skill_raw>``.
    """
    if ":" in skill_raw:
        return skill_raw
    pack = _BARE_TO_PACK.get(skill_raw, "core")
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

    def __init__(self, wf_key: str, dry_run: bool = False) -> None:
        self.wf_key = wf_key
        self.dry_run = dry_run

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
                if all_statuses <= {"completed", "skipped", "failed"}:
                    return "completed_with_failures"
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
        import json

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
            duration = round(time.monotonic() - t0, 2)

            if is_command_node and success:
                output = f"{node_id} executed via {specifier}"

            status = "completed" if success else "failed"
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

    def _update_node(
        self,
        node_id: str,
        status: str,
        output: str | None,
        duration: float | None = None,
    ) -> None:
        """Atomically update a node's status in workflows.json."""
        import json

        now = datetime.now(timezone.utc).isoformat()
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
