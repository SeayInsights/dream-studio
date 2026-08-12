#!/usr/bin/env python3
"""Hook: on-edit-enforce — SQLite authority enforcement on Edit|Write.

Trigger: PreToolUse (dedicated hooks.json entry — NOT the dispatcher, whose
stdout never reaches Claude Code; a deny decision must own the process stdout).

Denies edits to product source inside a registered project when that project
has no in_progress work order in the SQLite authority, with a reason naming
the exact command to run. Allowed edits are recorded to session state so
on-stop-enforce can verify the session's authority/docstore writes.

Fails open on every error path: no payload, no authority DB, import failure,
unregistered path — all allow. Honors the graduated tier (WO-ENFORCE-TIERS):
`DS_ENFORCE_TIER` ∈ off|observe|warn|enforce (default enforce); observe/warn
record the would-be deny and allow; DS_ENFORCE=0 is equivalent to off.
"""

from __future__ import annotations

import json
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


def _apply(tier: str, rule: str, reason: str, session_id: str | None) -> str:
    """Apply the graduated tier to a would-be denial (WO-ENFORCE-TIERS).

    ``enforce`` → deny (print the deny JSON, block the edit). ``observe``/``warn`` → record
    what WOULD have been denied — the SAME reason string — and ALLOW the edit; ``warn`` also
    surfaces the reason on stderr. Returns the decision string (``deny`` or ``observe``)."""
    if tier == "enforce":
        _deny(reason)
        return "deny"
    try:
        from runtime.lib import enforcement  # noqa: PLC0415

        enforcement.record_observation(
            hook_name="on_edit_enforce",
            hook_type="PreToolUse",
            rule=rule,
            reason=reason,
            tier=tier,
            session_id=session_id or None,
        )
    except Exception:
        pass  # observe recording is best-effort; the edit is allowed regardless
    if tier == "warn":
        print(reason, file=sys.stderr, flush=True)
    return "observe"


def _enforce(tier: str) -> tuple[str, str | None]:
    """Run the PreToolUse enforcement decision at the given tier.

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

        if kind == "docstore_only":
            # WO-FILESDB-P3 zero-disk: .planning working state lives in the files.db
            # docstore, never on disk. Deny the disk write and point at `ds files`.
            reason = (
                "[dream-studio] Zero-disk .planning: working notes, specs, plans, and"
                " reports are authored in the files.db docstore, never on disk. Use:\n"
                '  py -m interfaces.cli.ds files write "<name>" --category planning'
                " [--work-order <id>]\n"
                "  (read: ds files read <name>  ·  list: ds files list --category planning)\n"
                "Operator escape hatch: set DS_ENFORCE=0 (or run at a lower DS_ENFORCE_TIER)."
            )
            return (_apply(tier, "zero_disk_planning", reason, session_id), session_id)

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
            lines.append(
                "Operator escape hatch: set DS_ENFORCE=0 (or run at a lower DS_ENFORCE_TIER)."
            )
            return (_apply(tier, "authority_source_edit", "\n".join(lines), session_id), session_id)

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
    # Resolve the graduated tier. DS_ENFORCE=0 (or DS_ENFORCE_TIER=off) disables enforcement
    # AND its telemetry — the escape hatch is total. A broken enforcement lib fails open (no
    # enforcement), never blocks editing.
    try:
        from runtime.lib import enforcement  # noqa: PLC0415

        tier = enforcement.resolve_tier()
    except Exception:
        return
    if tier == "off":
        return

    started_at = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()
    decision = "allow"
    status = "success"
    error_msg: str | None = None
    session_id: str | None = None
    try:
        decision, session_id = _enforce(tier)
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
