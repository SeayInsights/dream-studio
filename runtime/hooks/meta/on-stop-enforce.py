#!/usr/bin/env python3
"""Hook: on-stop-enforce — session-end SQLite write verification.

Trigger: Stop (dedicated hooks.json entry — NOT the dispatcher, whose stdout
never reaches Claude Code; a block decision must own the process stdout).

Reads the session state recorded by on-edit-enforce and blocks the stop at
most once when:
- product source was edited but no authority write (task.completed /
  work_order.closed event, or a fresh done-task / closed-WO row) landed for
  the work order during the session, or
- a persistent documentation artifact (docs/**) was written without a matching
  ds_files record in files.db. (.planning/** is docstore-only under WO-FILESDB-P3
  — denied on disk at edit time, so it never reaches this check.)

The block reason names the exact remediation command for each violation.
Never blocks twice: respects stop_hook_active from the payload and a
stop_blocked_at marker in session state. Fails open on every error path.
Honors the graduated tier (WO-ENFORCE-TIERS): `DS_ENFORCE_TIER` ∈
off|observe|warn|enforce (default enforce); observe/warn record what would have
blocked and allow the stop; DS_ENFORCE=0 is equivalent to off.
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

_MAX_LISTED_VIOLATIONS = 8
# WO-HOOK-DRIFT-STOP: consecutive enforce-tier blocks before the stop is allowed
# loudly (stderr warning + recorded stop_bypassed mark). Bounded so a stuck
# session can always end; recorded so it can never end invisibly.
_MAX_STOP_BLOCKS = 3


def incomplete_task_count_or(enforcement, work_order_id: str, default: int = 1) -> int:
    """``incomplete_task_count`` with an unreadable answer treated as "tasks remain".

    None means the authority could not be read, or the work order has no tasks at all.
    Neither justifies telling the operator that everything is complete, so the caller
    falls back to the ordinary task-done guidance -- wrong-but-familiar beats a confident
    claim built on a query that answered nothing.
    """
    # getattr, not a direct call: the hook file and the enforcement library are SEPARATE
    # projected copies, so a tree can hold a new hook beside an older lib. Calling the
    # attribute directly made this raise AttributeError, which crashed two pre-existing
    # tests in test_wo_lifecycle_surface.py whose stub implements only
    # authority_write_since -- and would do the same in an install whose lib had not been
    # re-projected yet. Everything about propagation this session says that skew is the
    # normal state, not the exception, so the hook degrades to the ordinary guidance
    # instead of dying.
    counter = getattr(enforcement, "incomplete_task_count", None)
    if counter is None:
        return default
    remaining = counter(work_order_id)
    return default if remaining is None else remaining


def _authority_violations(enforcement, session: dict) -> list[str]:
    since = session.get("started_at", "")
    checked: set[str] = set()
    violations: list[str] = []
    for entry in session.get("source_edits", []):
        wo_id = entry.get("work_order_id")
        if not wo_id:
            continue
        # WO-WO-LIFECYCLE-SURFACE: AMBIGUITY IS SATISFIED BY EITHER CLAIMANT. When two
        # in-progress work orders both declare a module boundary over the edited file,
        # both are legitimately doing this work; demanding a write to the one the edit
        # hook happened to name would be a false violation, and false violations are what
        # push an operator to DS_ENFORCE=0. Pre-claimants session files carry only
        # work_order_id, so fall back to it.
        claimants = [c for c in (entry.get("claimants") or [wo_id]) if c]
        key = "|".join(sorted(claimants))
        if key in checked:
            continue
        checked.add(key)
        if any(enforcement.authority_write_since(c, since) for c in claimants):
            continue
        if len(claimants) > 1:
            others = ", ".join(claimants)
            # The achievable-remedy rule applies to BOTH branches. The first cut of this
            # fix patched only the single-claimant path below, so two work orders that
            # both cover the edited file and both have every task complete -- the exact
            # state this hook was corrected for -- still met the old impossible message.
            # in_progress_work_order's own docstring calls concurrent work orders normal
            # (three were in progress on the live authority when it was written), so this
            # is a reachable path, not a corner. Fixed for one caller and left open for
            # its sibling, in the fix for a defect about remedies that cannot be run.
            markable = [c for c in claimants if (incomplete_task_count_or(enforcement, c)) > 0]
            if markable:
                violations.append(
                    "Product source was edited under work orders whose module boundaries both"
                    f" cover it ({others}) but no authority write was recorded this session for"
                    " any of them. A write to ANY ONE satisfies this. Mark completed tasks:"
                    f" py -m interfaces.cli.ds work-order tasks {markable[0]}"
                    f" then py -m interfaces.cli.ds work-order task-done {markable[0]} <task_id>."
                )
            else:
                violations.append(
                    "Product source was edited under work orders whose module boundaries both"
                    f" cover it ({others}) but no authority write was recorded this session for"
                    " any of them. Every task on all of them is already complete, so there is"
                    " nothing to mark done. If this edit is NEW work, register it against the"
                    " one it belongs to:"
                    f" py -m interfaces.cli.ds work-order add-task {claimants[0]} --title ..."
                    " --acceptance TEST-CHECK:... A write to ANY ONE satisfies this."
                )
        else:
            # THE REMEDY MUST BE ONE THE OPERATOR CAN ACTUALLY PERFORM. This message
            # always prescribed `task-done <task_id>` with `close` as the alternative,
            # and both are impossible once every task is complete and the close gates
            # refuse -- the state that produced this fix. The operator was left with
            # inventing a task to mark done, which is the false-done this hook exists to
            # prevent, or disabling enforcement. Neither is a remedy.
            remaining = incomplete_task_count_or(enforcement, wo_id)
            if remaining == 0:
                violations.append(
                    "Product source was edited under work order"
                    f" {wo_id} but no authority write was recorded this session."
                    " Every task on it is already complete, so there is nothing to mark"
                    " done. If this edit is NEW work, register it:"
                    f" py -m interfaces.cli.ds work-order add-task {wo_id} --title ..."
                    " --acceptance TEST-CHECK:... That records it and satisfies this."
                    " If the work is finished, close it once its gates pass:"
                    f" py -m interfaces.cli.ds work-order close {wo_id}."
                )
            else:
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
            # THE SAME ACHIEVABLE-REMEDY RULE AS _authority_violations, in its sibling.
            # `ds files add` hard-requires path.is_file() and returns
            # {"ok": false, "error": "not a file: ..."} otherwise, so prescribing it for
            # an artifact that has since been deleted or moved hands the operator a
            # command that cannot succeed. A Bash `rm`/`mv` never reaches the PreToolUse
            # Write|Edit hook, so the session can genuinely record an edit to a file that
            # is gone by the time the stop runs. Found by independent review as the third
            # instance of this shape in this work order.
            if not Path(path).is_file():
                # Says only what is true. A first draft ended "if it was deleted
                # deliberately, nothing is owed and this clears once the session records
                # no edit to it" -- and independent review proved that false: nothing in
                # the repo ever removes an entry from doc_edits, so the recorded edit is
                # permanent for the life of the session_id. The violation does not clear;
                # it re-blocks each stop until _MAX_STOP_BLOCKS, then passes loudly with a
                # recorded stop_bypassed. An untrue reassurance inside a blocking message
                # is worse than none, and writing one in a fix about achievable remedies
                # was the same error one level up.
                violations.append(
                    f"Documentation artifact {path} was edited this session, has no"
                    " files.db record, and is no longer on disk, so it cannot be"
                    " registered as-is. If it was renamed, register the current path:"
                    ' py -m interfaces.cli.ds files add "<new path>"'
                    f" --project-id {project_id}. If it was deleted deliberately, this"
                    f" session has nothing left to record for it: the edit stays on the"
                    " session record, so this will block up to"
                    f" {_MAX_STOP_BLOCKS} stops and then pass with a recorded bypass."
                )
            else:
                violations.append(
                    f"Documentation artifact {path} has no files.db record."
                    f' Register it: py -m interfaces.cli.ds files add "{path}"'
                    f" --project-id {project_id}"
                )
    return violations


def _enforce(tier: str) -> tuple[str, str | None]:
    """Run the Stop enforcement decision at the given tier.

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

        # WO-HOOK-DRIFT-STOP: the old one-shot (`stop_blocked_at` set → noop)
        # let the SECOND stop through unconditionally — the weakest remediation
        # was simply stopping again. Now every stop RE-VALIDATES: violations
        # resolved → allow; still present → re-block, capped at
        # _MAX_STOP_BLOCKS consecutive blocks, after which the stop is allowed
        # LOUDLY with a recorded stop_bypassed mark (never an infinite lock,
        # never a silent pass-through).
        violations = _authority_violations(enforcement, session)
        violations += _docstore_violations(enforcement, session)

        if not violations:
            enforcement.delete_session(session_id)
            enforcement.gc_session_files()
            return ("allow", session_id)

        shown = violations[:_MAX_LISTED_VIOLATIONS]
        if len(violations) > len(shown):
            shown.append(f"...and {len(violations) - len(shown)} more.")
        reason = (
            "[dream-studio] SQLite enforcement: this session has unrecorded work.\n"
            + "\n".join(f"- {v}" for v in shown)
            + "\nResolve the items above (or set DS_ENFORCE=0, or lower DS_ENFORCE_TIER),"
            " then stop again."
        )
        block_count = int(session.get("stop_block_count") or 0)
        if tier == "enforce" and block_count >= _MAX_STOP_BLOCKS:
            try:
                enforcement.record_bypass(
                    hook_name="on_stop_enforce",
                    hook_type="Stop",
                    rule="stop_bypassed",
                    detail=(
                        f"{len(violations)} violation(s) still unresolved after"
                        f" {block_count} consecutive blocks — stop allowed loudly"
                    ),
                    session_id=session_id,
                )
            except Exception:
                pass
            print(
                f"[dream-studio] WARNING: stop allowed after {block_count} blocks with"
                f" unresolved work (recorded as stop_bypassed).\n{reason}",
                file=sys.stderr,
                flush=True,
            )
            enforcement.delete_session(session_id)
            enforcement.gc_session_files()
            return ("observe", session_id)
        if tier == "enforce":
            session["stop_blocked_at"] = enforcement.now_iso()
            session["stop_block_count"] = block_count + 1
            enforcement.save_session(session_id, session)
            print(json.dumps({"decision": "block", "reason": reason}), flush=True)
            return ("block", session_id)
        # observe/warn (WO-ENFORCE-TIERS): record what WOULD have blocked the stop — the same
        # reason string — and ALLOW the session to end; warn also surfaces it on stderr.
        enforcement.record_observation(
            hook_name="on_stop_enforce",
            hook_type="Stop",
            rule="stop_unrecorded_work",
            reason=reason,
            tier=tier,
            session_id=session_id,
        )
        if tier == "warn":
            print(reason, file=sys.stderr, flush=True)
        enforcement.delete_session(session_id)
        enforcement.gc_session_files()
        return ("observe", session_id)
    except Exception:
        return ("error", session_id)


def main() -> None:
    # Resolve the graduated tier. DS_ENFORCE=0 (or DS_ENFORCE_TIER=off) disables enforcement
    # AND its telemetry — the escape hatch is total. A broken enforcement lib fails open.
    try:
        from runtime.lib import enforcement  # noqa: PLC0415

        tier = enforcement.resolve_tier()
    except Exception:
        return
    if tier == "off":
        # WO-BYPASS-TELEMETRY: record the suppressed stop-enforcement before the
        # short-circuit. Emission failures never block.
        try:
            enforcement.record_bypass(
                hook_name="on_stop_enforce",
                hook_type="Stop",
                rule="enforcement_disabled",
                detail="DS_ENFORCE=0 / DS_ENFORCE_TIER=off — stop enforcement short-circuited",
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
