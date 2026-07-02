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


def main() -> None:
    if os.environ.get("DS_ENFORCE", "").strip() == "0":
        return

    try:
        raw = sys.stdin.read().lstrip("﻿")
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return

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
        return

    try:
        from runtime.lib import enforcement  # noqa: PLC0415
    except Exception:
        return

    try:
        project = enforcement.match_registered_project(file_path)
        if project is None:
            return

        kind = enforcement.classify_path(file_path, project["project_path"])
        if kind == "exempt":
            return

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
            return

        if session_id:
            enforcement.record_edit(
                session_id,
                file_path=file_path,
                kind=kind,
                project_id=project["project_id"],
                work_order_id=wo["work_order_id"] if wo else None,
            )
    except Exception:
        return


if __name__ == "__main__":
    main()
