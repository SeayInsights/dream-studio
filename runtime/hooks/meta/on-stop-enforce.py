#!/usr/bin/env python3
"""Hook: on-stop-enforce — session-end SQLite write verification.

Trigger: Stop (dedicated hooks.json entry — NOT the dispatcher, whose stdout
never reaches Claude Code; a block decision must own the process stdout).

Reads the session state recorded by on-edit-enforce and blocks the stop at
most once when:
- product source was edited but no authority write (task.completed /
  work_order.closed event, or a fresh done-task / closed-WO row) landed for
  the work order during the session, or
- a persistent documentation artifact (docs/**, .planning/** excluding
  personal/) was written without a matching ds_files record in files.db.

The block reason names the exact remediation command for each violation.
Never blocks twice: respects stop_hook_active from the payload and a
stop_blocked_at marker in session state. Fails open on every error path.
DS_ENFORCE=0 disables enforcement entirely.
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

_MAX_LISTED_VIOLATIONS = 8


def _authority_violations(enforcement, session: dict) -> list[str]:
    since = session.get("started_at", "")
    checked: set[str] = set()
    violations: list[str] = []
    for entry in session.get("source_edits", []):
        wo_id = entry.get("work_order_id")
        if not wo_id or wo_id in checked:
            continue
        checked.add(wo_id)
        if not enforcement.authority_write_since(wo_id, since):
            violations.append(
                "Product source was edited under work order"
                f" {wo_id} but no authority write was recorded this session."
                " Mark completed tasks:"
                f" py -m interfaces.cli.ds work-order tasks {wo_id}"
                f" then py -m interfaces.cli.ds work-order task-done {wo_id} <task_id>"
                f" (or close: py -m interfaces.cli.ds work-order close {wo_id})."
            )
    return violations


def _docstore_violations(enforcement, session: dict) -> list[str]:
    violations: list[str] = []
    for entry in session.get("doc_edits", []):
        path = entry.get("path", "")
        if not path:
            continue
        # The registration must be at least as fresh as the session's last
        # edit to the artifact — a stale record does not cover new content.
        since = entry.get("ts") or session.get("started_at", "")
        name_hint = Path(path).name
        if not enforcement.docstore_record_since(name_hint, since):
            project_id = entry.get("project_id", "<project_id>")
            violations.append(
                f"Documentation artifact {path} has no files.db record."
                f' Register it: py -m interfaces.cli.ds files add "{path}"'
                f" --project-id {project_id}"
            )
    return violations


def _enforce() -> tuple[str, str | None]:
    """Run the Stop enforcement decision.

    Returns ``(decision, session_id)``: ``block`` (stop blocked with violations),
    ``allow`` (session clean, state cleared), ``noop`` (re-entrant / no session /
    unparseable payload), or ``error`` (fail-open). Prints the block JSON to stdout
    on the block path — callers must not write stdout.
    """
    session_id: str | None = None
    try:
        raw = sys.stdin.read().lstrip("﻿")
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return ("noop", None)

    if payload.get("stop_hook_active"):
        return ("noop", None)
    session_id = payload.get("session_id", "")
    if not session_id:
        return ("noop", None)

    try:
        from runtime.lib import enforcement  # noqa: PLC0415
    except Exception:
        return ("noop", session_id)

    try:
        session = enforcement.load_session(session_id)
        if not session:
            return ("noop", session_id)
        if session.get("stop_blocked_at"):
            return ("noop", session_id)

        violations = _authority_violations(enforcement, session)
        violations += _docstore_violations(enforcement, session)

        if not violations:
            enforcement.delete_session(session_id)
            enforcement.gc_session_files()
            return ("allow", session_id)

        shown = violations[:_MAX_LISTED_VIOLATIONS]
        if len(violations) > len(shown):
            shown.append(f"...and {len(violations) - len(shown)} more.")
        session["stop_blocked_at"] = enforcement.now_iso()
        enforcement.save_session(session_id, session)
        reason = (
            "[dream-studio] SQLite enforcement: this session has unrecorded work.\n"
            + "\n".join(f"- {v}" for v in shown)
            + "\nResolve the items above (or set DS_ENFORCE=0), then stop again."
        )
        print(json.dumps({"decision": "block", "reason": reason}), flush=True)
        return ("block", session_id)
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
        # the block/allow decision or the process stdout.
        try:
            from runtime.lib import enforcement  # noqa: PLC0415

            enforcement.log_hook_execution(
                hook_name="on_stop_enforce",
                hook_type="Stop",
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
