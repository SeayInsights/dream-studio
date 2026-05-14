"""Workflow progress tracking library for on-workflow-progress hook.

Extracts workflow state reading and status reporting logic from hook to comply
with constitutional requirement that hooks be <50 lines.
"""

from __future__ import annotations

import json
from pathlib import Path

SCHEMA_VERSION = 1


def load_active_workflows(state_dir: Path) -> dict[str, dict]:
    """Load and filter to active workflows from workflows.json.

    Returns:
        Dict mapping workflow_id to workflow data for active workflows only.
        Returns empty dict if file doesn't exist, is invalid, or has no active workflows.
    """
    state_file = state_dir / "workflows.json"
    if not state_file.is_file():
        return {}

    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    if data.get("schema_version", 1) > SCHEMA_VERSION:
        return {}

    active = {}
    for key, wf in data.get("active_workflows", {}).items():
        status = wf.get("status", "unknown")
        if status not in ("completed", "aborted"):
            active[key] = wf

    return active


def print_workflow_status(workflow_id: str, workflow_data: dict) -> None:
    """Print workflow status summary and emit JSON event.

    Args:
        workflow_id: Workflow identifier
        workflow_data: Workflow state dict with nodes, status, gates, etc.
    """
    status = workflow_data.get("status", "unknown")
    name = workflow_data.get("workflow", workflow_id)
    nodes = workflow_data.get("nodes", {})

    total = len(nodes)
    done = sum(1 for n in nodes.values() if n.get("status") in ("completed", "skipped"))
    running = [nid for nid, n in nodes.items() if n.get("status") == "running"]
    pending_gates = workflow_data.get("gates_pending", [])

    print(f"\n[workflow] {name} — {status} ({done}/{total} nodes done)", flush=True)
    if running:
        print(f"  -> Running: {', '.join(running)}", flush=True)
    if pending_gates:
        print(f"  -> Gates pending: {', '.join(pending_gates)}", flush=True)

    print(
        json.dumps(
            {
                "type": "workflow-progress",
                "workflow": name,
                "status": status,
                "current_node": workflow_data.get("current_node"),
                "completed": done,
                "total": total,
            }
        ),
        flush=True,
    )
