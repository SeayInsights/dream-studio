"""Workflow state JSON I/O — schema, paths, locking, read/write/checkpoint.

WO-GF-CONTROL-INSTALL-split: implementation moved to state_{io,telemetry,
commands}.py; control/execution/workflow/state.py re-exports the
public+private surface so existing
`from control.execution.workflow.state import X` callers are unchanged.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, UTC
from pathlib import Path

from core.config import paths
from control.execution.workflow.engine import _file_lock

SCHEMA_VERSION = 1
_TERMINAL = frozenset({"completed", "completed_with_failures", "aborted"})


# ── State I/O ─────────────────────────────────────────────────────


def _state_path() -> Path:
    return paths.state_dir() / "workflows.json"


def _checkpoint_path() -> Path:
    return paths.state_dir() / "workflow-checkpoint.json"


def _state_lock():
    """Lock for atomic read-modify-write on workflows.json."""
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    return _file_lock(p.parent / f"{p.name}.lock")


def _read_state() -> dict:
    p = _state_path()
    if not p.is_file():
        return {"schema_version": SCHEMA_VERSION, "active_workflows": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if data.get("schema_version", 1) > SCHEMA_VERSION:
            print(
                f"Error: workflows.json schema_version {data.get('schema_version')} "
                f"exceeds supported ({SCHEMA_VERSION})",
                file=sys.stderr,
            )
            sys.exit(1)
        return data
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error reading workflows.json: {e}", file=sys.stderr)
        sys.exit(1)


def _write_state(data: dict) -> None:
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    out = {**data, "schema_version": SCHEMA_VERSION}
    p.write_text(json.dumps(out, indent=2), encoding="utf-8")


def _write_checkpoint(workflow_key: str, node_id: str | None, status: str) -> None:
    p = _checkpoint_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {
                "workflow_key": workflow_key,
                "last_node": node_id,
                "status": status,
                "timestamp": datetime.now(UTC).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _get_workflow(data: dict, key: str) -> dict:
    wf = data.get("active_workflows", {}).get(key)
    if not wf:
        print(f"Error: workflow '{key}' not found", file=sys.stderr)
        sys.exit(1)
    return wf
