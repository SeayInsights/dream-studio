#!/usr/bin/env python3
"""Hook: on-workflow-progress — read-only workflow status reporter.

Trigger: Stop event.
Reads ~/.dream-studio/state/workflows.json (written by Chief-of-Staff
during workflow execution) and prints a summary if any workflow is active.
This hook NEVER writes state — Chief-of-Staff owns the state file.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _get_plugin_root() -> Path:
    sidecar = Path(__file__).resolve()
    for _ in range(8):
        candidate = sidecar / ".plugin-root"
        if candidate.is_file():
            try:
                return Path(candidate.read_text(encoding="utf-8").strip()).resolve()
            except Exception:
                pass
        sidecar = sidecar.parent
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[4]


_PLUGIN_ROOT = _get_plugin_root()
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))
if str(_PLUGIN_ROOT / "hooks") not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT / "hooks"))

from core.config import paths
from control.execution.workflow import tracking as workflow_tracking  # noqa: E402


def main() -> None:
    workflows = workflow_tracking.load_active_workflows(paths.state_dir())
    if not workflows:
        return

    for workflow_id, workflow_data in workflows.items():
        workflow_tracking.print_workflow_status(workflow_id, workflow_data)


if __name__ == "__main__":
    main()
