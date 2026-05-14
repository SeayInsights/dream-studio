#!/usr/bin/env python3
"""Hook: on-workflow-progress — read-only workflow status reporter.

Trigger: Stop event.
Reads ~/.dream-studio/state/workflows.json (written by Chief-of-Staff
during workflow execution) and prints a summary if any workflow is active.
This hook NEVER writes state — Chief-of-Staff owns the state file.
"""

from __future__ import annotations

import sys
from pathlib import Path

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
