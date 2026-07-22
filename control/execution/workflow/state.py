#!/usr/bin/env python3
"""Workflow state management CLI.

Chief-of-Staff calls these commands during workflow execution instead
of manually reading/editing JSON. One Bash call per state change.

Commands:
  start  <name> <yaml-path>                          → init workflows.json, print key
  update <key> <node-id> <status> [--output] [--duration]  → update node
  pause  <key> <node-id> <gate-name>                  → pause at gate
  resume <key>                                         → resume from gate
  abort  <key>                                         → cancel workflow
  status [<key>]                                       → print state
  eval   <key> <expression>                            → evaluate condition, exit 0=true 1=false
  next   <key>                                         → list nodes ready to execute

Pure evaluation logic lives in workflow_engine.py. This module handles
all CLI parsing, state I/O, and command dispatch.

WO-GF-CONTROL-INSTALL-split: implementation moved to state_{io,telemetry,
commands}.py; this module re-exports the public+private surface so existing
`from control.execution.workflow.state import X` callers are unchanged. This
module is also a CLI entry point (`py -m control.execution.workflow.state`),
so the sys.path bootstrap and the `if __name__ == "__main__"` dispatch stay
on this facade — `-m` sets `__name__ == "__main__"` on the facade module
specifically, not on state_commands.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from .state_commands import (  # noqa: E402
    _find_resumable,
    cmd_abort,
    cmd_eval,
    cmd_next,
    cmd_pause,
    cmd_resume,
    cmd_start,
    cmd_status,
    cmd_update,
    main,
)
from .state_commands import _COST_AVAILABLE  # noqa: E402
from .state_io import (  # noqa: E402
    SCHEMA_VERSION,
    _TERMINAL,
    _checkpoint_path,
    _get_workflow,
    _read_state,
    _state_lock,
    _state_path,
    _write_checkpoint,
    _write_state,
)
from .state_telemetry import (  # noqa: E402
    _duration_ms,
    _emit_canonical_workflow_events,
    _emit_execution_events_telemetry,
    _emit_workflow_completion,
    _generate_repo_context,
    _try_archive_and_prune,
)

__all__ = [
    "SCHEMA_VERSION",
    "_COST_AVAILABLE",
    "_TERMINAL",
    "_checkpoint_path",
    "_duration_ms",
    "_emit_canonical_workflow_events",
    "_emit_execution_events_telemetry",
    "_emit_workflow_completion",
    "_find_resumable",
    "_generate_repo_context",
    "_get_workflow",
    "_read_state",
    "_state_lock",
    "_state_path",
    "_try_archive_and_prune",
    "_write_checkpoint",
    "_write_state",
    "cmd_abort",
    "cmd_eval",
    "cmd_next",
    "cmd_pause",
    "cmd_resume",
    "cmd_start",
    "cmd_status",
    "cmd_update",
    "main",
]


if __name__ == "__main__":
    main()
