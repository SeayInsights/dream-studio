"""Exit 0 when the active work order has no pending tasks, 1 when it does.

A completion check for the orchestrator's `implement-tasks` node, and it exists because
the obvious version was wrong. That node's effect is "every task on this work order is
done", which the AUTHORITY knows and the agent's own report does not establish. The first
attempt asked `ds project state` for the substring `"pending_tasks": 0,` -- which appears
**30 times** in that output, once per work order in the ready set. It passed whenever ANY
work order anywhere had nothing pending, so it could not fail for the reason it existed.

Reading the field inside `next_work_order` is the difference between checking the active
work order and checking that the fleet contains a finished one.

Exit codes: 0 = no pending tasks; 1 = pending tasks remain, or the state could not be read.
Never 0 on an error -- a check that cannot see the answer has not found it satisfied.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_TIMEOUT = 45


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "interfaces.cli.ds", "project", "state"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"could not read project state: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if proc.returncode != 0:
        print(f"ds project state exited {proc.returncode}", file=sys.stderr)
        return 1

    try:
        state = json.loads(proc.stdout)
    except (TypeError, ValueError) as exc:
        print(f"project state was not JSON: {exc}", file=sys.stderr)
        return 1

    projects = state.get("projects") or []
    if not projects:
        print("no active project", file=sys.stderr)
        return 1

    work_order = projects[0].get("next_work_order") or {}
    if not work_order:
        print("no active work order", file=sys.stderr)
        return 1

    pending = work_order.get("pending_tasks")
    title = str(work_order.get("title") or "")[:60]
    if pending == 0:
        print(f"TASKS_DONE: {title} has no pending tasks")
        return 0

    print(f"{pending} task(s) still pending on {title!r}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
