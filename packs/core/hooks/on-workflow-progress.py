#!/usr/bin/env python3
"""Hook: on-workflow-progress — read-only workflow status reporter.

Trigger: Stop event.
Reads ~/.dream-studio/state/workflows.json (written by Chief-of-Staff
during workflow execution) and prints a summary if any workflow is active.
This hook NEVER writes state — Chief-of-Staff owns the state file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hooks"))

from lib import paths  # noqa: E402

SCHEMA_VERSION = 1


def main() -> None:
    state_file = paths.state_dir() / "workflows.json"
    if not state_file.is_file():
        return

    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    if data.get("schema_version", 1) > SCHEMA_VERSION:
        return

    for key, wf in data.get("active_workflows", {}).items():
        status = wf.get("status", "unknown")
        if status in ("completed", "aborted"):
            continue

        name = wf.get("workflow", key)
        nodes = wf.get("nodes", {})
        total = len(nodes)
        done = sum(1 for n in nodes.values() if n.get("status") in ("completed", "skipped"))
        running = [nid for nid, n in nodes.items() if n.get("status") == "running"]
        pending_gates = wf.get("gates_pending", [])

        print(f"\n[workflow] {name} — {status} ({done}/{total} nodes done)", flush=True)
        if running:
            print(f"  -> Running: {', '.join(running)}", flush=True)
        if pending_gates:
            print(f"  -> Gates pending: {', '.join(pending_gates)}", flush=True)

        print(json.dumps({
            "type": "workflow-progress",
            "workflow": name,
            "status": status,
            "current_node": wf.get("current_node"),
            "completed": done,
            "total": total,
        }), flush=True)


if __name__ == "__main__":
    main()
