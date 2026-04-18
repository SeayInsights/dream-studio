#!/usr/bin/env python3
"""Hook: on-workflow-progress — track workflow node completion.

Trigger: Stop event.
Reads/writes ~/.dream-studio/state/workflows.json to maintain
per-workflow state. Prints a structured summary line for Chief-of-Staff
to ingest and a human-readable progress line for the Director.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import paths  # noqa: E402

SCHEMA_VERSION = 1
WORKFLOWS_FILENAME = "workflows.json"


def _workflows_path() -> Path:
    return paths.state_dir() / WORKFLOWS_FILENAME


def read_workflows() -> Dict[str, Any]:
    path = _workflows_path()
    if not path.is_file():
        return {"schema_version": SCHEMA_VERSION, "active_workflows": {}}
    try:
        with path.open("r", encoding="utf-8") as f:
            doc = json.load(f)
        stored = doc.get("schema_version", 1)
        if not isinstance(stored, int) or stored > SCHEMA_VERSION:
            return {"schema_version": SCHEMA_VERSION, "active_workflows": {}}
        return doc
    except (json.JSONDecodeError, OSError):
        return {"schema_version": SCHEMA_VERSION, "active_workflows": {}}


def write_workflows(data: Dict[str, Any]) -> Path:
    path = _workflows_path()
    data["schema_version"] = SCHEMA_VERSION
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return path


def update_node(
    data: Dict[str, Any],
    workflow_key: str,
    node_id: str,
    status: str,
    output: Optional[str] = None,
    duration_s: Optional[float] = None,
) -> Dict[str, Any]:
    workflows = data.get("active_workflows", {})
    if workflow_key not in workflows:
        return data

    wf = workflows[workflow_key]
    nodes = wf.get("nodes", {})
    now = datetime.now(timezone.utc).isoformat()

    node_state = nodes.get(node_id, {})
    node_state["status"] = status

    if status == "running" and "started" not in node_state:
        node_state["started"] = now
    if output is not None:
        node_state["output"] = output
    if duration_s is not None:
        node_state["duration_s"] = duration_s
    if status in ("completed", "failed", "skipped"):
        node_state["finished"] = now

    nodes[node_id] = node_state
    wf["nodes"] = nodes
    wf["current_node"] = node_id

    completed = sum(1 for n in nodes.values() if n.get("status") in ("completed", "skipped"))
    total = len(nodes)
    if completed == total:
        wf["status"] = "completed"
    elif any(n.get("status") == "running" for n in nodes.values()):
        wf["status"] = "running"

    workflows[workflow_key] = wf
    data["active_workflows"] = workflows
    return data


def workflow_summary(data: Dict[str, Any]) -> Optional[str]:
    workflows = data.get("active_workflows", {})
    if not workflows:
        return None

    lines = []
    for key, wf in workflows.items():
        if wf.get("status") in ("completed", "aborted"):
            continue

        name = wf.get("workflow", key)
        status = wf.get("status", "unknown")
        nodes = wf.get("nodes", {})
        total = len(nodes)
        completed = sum(1 for n in nodes.values() if n.get("status") in ("completed", "skipped"))
        running = [nid for nid, n in nodes.items() if n.get("status") == "running"]
        pending_gates = wf.get("gates_pending", [])

        lines.append(f"[workflow] {name} — {status} ({completed}/{total} nodes done)")

        if running:
            lines.append(f"  -> Running: {', '.join(running)}")

        blocked = [nid for nid, n in nodes.items() if n.get("status") == "blocked_by_deps"]
        if blocked:
            lines.append(f"  -> Waiting: {', '.join(blocked[:5])}")

        if pending_gates:
            lines.append(f"  -> Gates pending: {', '.join(pending_gates)}")

    return "\n".join(lines) if lines else None


def main() -> None:
    data = read_workflows()
    workflows = data.get("active_workflows", {})

    if not workflows:
        return

    has_active = any(
        wf.get("status") in ("running", "paused")
        for wf in workflows.values()
    )
    if not has_active:
        return

    summary = workflow_summary(data)
    if summary:
        print(f"\n{summary}", flush=True)

        for key, wf in workflows.items():
            if wf.get("status") in ("completed", "aborted"):
                continue
            nodes = wf.get("nodes", {})
            total = len(nodes)
            completed = sum(1 for n in nodes.values() if n.get("status") in ("completed", "skipped"))
            print(json.dumps({
                "type": "workflow-progress",
                "workflow": wf.get("workflow", key),
                "status": wf.get("status", "unknown"),
                "current_node": wf.get("current_node"),
                "completed": completed,
                "total": total,
                "gates_pending": wf.get("gates_pending", []),
            }), flush=True)


if __name__ == "__main__":
    main()
