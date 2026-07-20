#!/usr/bin/env python3
"""Hook: on-edit-enforce — SQLite authority enforcement on Edit|Write.

Trigger: PreToolUse (dedicated hooks.json entry — NOT the dispatcher, whose
stdout never reaches Claude Code; a deny decision must own the process stdout).

Denies edits to product source inside a registered project when that project
has no in_progress work order in the SQLite authority, with a reason naming
the exact command to run. Allowed edits are recorded to session state so
on-stop-enforce can verify the session's authority/docstore writes.

Fails open on every error path: no payload, no authority DB, import failure,
unregistered path — all allow. DS_ENFORCE=0 disables enforcement entirely.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[3]
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))
# Installed trees may lack runtime/lib — fall back to the repo via sidecar.
_sidecar = _PLUGIN_ROOT / ".ds-source-root"
if _sidecar.is_file():
    try:
        _src = _sidecar.read_text(encoding="utf-8").strip()
        if _src and _src not in sys.path:
            sys.path.append(_src)
    except OSError:
        pass


def _deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        ),
        flush=True,
    )


def _enforce() -> tuple[str, str | None]:
    """Run the PreToolUse enforcement decision.

    Returns ``(decision, session_id)`` where decision is one of ``allow`` (edit
    permitted / recorded), ``deny`` (product-source edit blocked), ``noop`` (path
    not subject to enforcement / unparseable payload), or ``error`` (fail-open).
    Prints the deny JSON to stdout on the deny path — callers must not write stdout.
    """
    session_id: str | None = None
    try:
        raw = sys.stdin.read().lstrip("﻿")
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return ("noop", None)

    tool_input = payload.get("tool_input", {})
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except Exception:
            tool_input = {}
    file_path = (
        tool_input.get("file_path")
        or tool_input.get("notebook_path")
        or tool_input.get("path")
        or ""
    )
    if not file_path:
        return ("noop", None)

    try:
        from runtime.lib import enforcement  # noqa: PLC0415
    except Exception:
        return ("noop", None)

    try:
        project = enforcement.match_registered_project(file_path)
        if project is None:
            return ("noop", None)

        kind = enforcement.classify_path(file_path, project["project_path"])
        if kind == "exempt":
            return ("noop", None)

        session_id = payload.get("session_id", "")
        wo = enforcement.in_progress_work_order(project["project_id"])

        if wo is None and kind == "source":
            nxt = enforcement.next_created_work_order(project["project_id"])
            lines = [
                "[dream-studio] Authority enforcement: no work order is in_progress"
                f" for project '{project['name']}'. Product-source edits require an"
                " active work order in the SQLite authority.",
            ]
            if nxt is not None:
                lines.append(
                    f"Run: py -m interfaces.cli.ds work-order start {nxt['work_order_id']}"
                    f"  (next: {nxt['title']})"
                )
            lines.append(
                "Or list work orders: py -m interfaces.cli.ds work-order list"
                f" {project['project_id']}"
            )
            lines.append("Operator escape hatch: set DS_ENFORCE=0.")
            _deny("\n".join(lines))
            return ("deny", session_id)

        if session_id:
            enforcement.record_edit(
                session_id,
                file_path=file_path,
                kind=kind,
                project_id=project["project_id"],
                work_order_id=wo["work_order_id"] if wo else None,
            )
        return ("allow", session_id)
    except Exception:
        return ("error", session_id)


def main() -> None:
    # DS_ENFORCE=0 disables enforcement AND its telemetry — the escape hatch is total.
    if os.environ.get("DS_ENFORCE", "").strip() == "0":
        return

    started_at = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()
    decision = "allow"
    status = "success"
    error_msg: str | None = None
    session_id: str | None = None
    try:
        decision, session_id = _enforce()
        if decision == "error":
            # _enforce's internal fail-open swallowed an exception — record the run
            # as failed so the stats view does not report it as a clean success.
            status = "failed"
    except Exception as exc:  # pragma: no cover - _enforce is already guarded
        status = "failed"
        error_msg = str(exc)
    finally:
        # WO-HOOK-ENFORCE-EXEC-STATS: record this directly-wired hook's execution so
        # it appears in the DuckDB hook_executions view. Best-effort; never affects
        # the deny/allow decision or the process stdout.
        try:
            from runtime.lib import enforcement  # noqa: PLC0415

            enforcement.log_hook_execution(
                hook_name="on_edit_enforce",
                hook_type="PreToolUse",
                started_at=started_at,
                duration_ms=int((time.monotonic() - start) * 1000),
                decision=decision,
                status=status,
                error_message=error_msg,
                session_id=session_id or None,
            )
        except Exception:
            pass


if __name__ == "__main__":
    main()
