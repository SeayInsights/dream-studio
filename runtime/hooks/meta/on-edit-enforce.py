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

    try:
        from runtime.lib import enforcement  # noqa: PLC0415
    except Exception:
        # WO-BYPASS-TELEMETRY: the enforcement lib failed to import — enforcement
        # silently fails open. Record the fail-open through the event writer
        # directly (the lib that would normally record it is the thing that broke).
        try:
            from core.event_store.event_writer import insert_hook_execution  # noqa: PLC0415

            _now = datetime.now(timezone.utc).isoformat()
            insert_hook_execution(
                hook_name="on_edit_enforce",
                hook_type="PreToolUse",
                trigger_context={
                    "decision": "bypass",
                    "rule": "fail_open_lib_import",
                    "detail": "runtime.lib.enforcement import failed — edit allowed unenforced",
                },
                started_at=_now,
                completed_at=_now,
                duration_ms=0,
                exit_code=0,
                status="success",
                session_id=None,
            )
        except Exception:
            pass
        return ("noop", None)

    session_id = payload.get("session_id", "")

    # WO-HOOK-COVERAGE: candidates come from three tool families — direct file
    # tools (file_path/notebook_path), MCP write tools (path), and Bash/PowerShell
    # commands, whose write targets are extracted best-effort. A write-shaped
    # command with no resolvable target records an unparsed_write visibility
    # event and allows (fail-open stays; invisibility does not).
    file_path = (
        tool_input.get("file_path")
        or tool_input.get("notebook_path")
        or tool_input.get("path")
        or ""
    )
    candidates = [file_path] if file_path else []
    _command = tool_input.get("command") or ""
    if not candidates and (payload.get("tool_name") == "Bash" or _command):
        try:
            targets, has_write = enforcement.extract_write_targets(_command)
        except Exception:
            return ("noop", session_id)
        if targets:
            candidates = targets
        else:
            if has_write:
                try:
                    enforcement.record_bypass(
                        hook_name="on_edit_enforce",
                        hook_type="PreToolUse",
                        rule="unparsed_write",
                        detail=f"write-shaped command, no resolvable target: {_command[:300]}",
                        session_id=session_id or None,
                    )
                except Exception:
                    pass
            return ("noop", session_id)
    if not candidates:
        return ("noop", None)

    try:
        decision = "noop"
        for cand in candidates:
            project = enforcement.match_registered_project(cand)
            if project is None:
                continue

            kind = enforcement.classify_path(cand, project["project_path"])
            if kind == "exempt":
                continue

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

            # WO-WO-LIFECYCLE-SURFACE: pass the path so attribution can go by declared
            # module boundary. Without it the newest-started work order claims every
            # edit, and the stop hook then demands an authority write against a work
            # order the session never touched.
            wo = enforcement.in_progress_work_order(
                project["project_id"],
                file_path=cand,
                project_path=project["project_path"],
            )

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
                return (
                    _apply(tier, "authority_source_edit", "\n".join(lines), session_id),
                    session_id,
                )

            # WO-HOOK-COVERAGE: module_boundary advisory — the WO's declared
            # boundary was pure prose before; edits outside it are now recorded
            # (observe tier, never a deny) so scope drift is visible.
            if wo is not None and kind == "source":
                try:
                    globs = enforcement.boundary_globs(wo.get("description", ""))
                    if globs and not enforcement.path_in_boundary(
                        cand, project["project_path"], globs
                    ):
                        enforcement.record_observation(
                            hook_name="on_edit_enforce",
                            hook_type="PreToolUse",
                            rule="module_boundary_advisory",
                            reason=(
                                f"edit outside the module boundary of WO"
                                f" {wo['work_order_id'][:8]} ({wo['title'][:60]}): {cand}"
                            ),
                            tier="observe",
                            session_id=session_id or None,
                        )
                except Exception:
                    pass  # advisory only — never affects the decision

            if session_id:
                enforcement.record_edit(
                    session_id,
                    file_path=cand,
                    kind=kind,
                    project_id=project["project_id"],
                    work_order_id=wo["work_order_id"] if wo else None,
                    claimants=(wo or {}).get("claimants"),
                    # Carry HOW the work order was chosen. A boundary match and a
                    # recency guess are different claims, and the stop hook must not
                    # present the second with the confidence of the first.
                    attribution=(wo or {}).get("attribution"),
                )
            decision = "allow"
        return (decision, session_id)
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
        # WO-BYPASS-TELEMETRY: the escape hatch still works, but it leaves a mark —
        # every enforcement decision suppressed by DS_ENFORCE=0 / tier=off is
        # recorded before the short-circuit. Emission failures never block.
        try:
            enforcement.record_bypass(
                hook_name="on_edit_enforce",
                hook_type="PreToolUse",
                rule="enforcement_disabled",
                detail="DS_ENFORCE=0 / DS_ENFORCE_TIER=off — edit enforcement short-circuited",
            )
        except Exception:
            pass
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
