"""Work-order start composer.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/start.py``. Holds
``start_work_order`` — reads (or accepts pre-read) brief data, enforces the
no-brief-for-UI and milestone-ordering guards, writes context.md, updates the
row to in_progress, emits the ``work_order.started`` spool event, and returns
a result dict. No logic changes — extracted verbatim from the original
module.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect

from .start_shared import _check_sequence_order


def start_work_order(
    *,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
    planning_root: Path | None = None,
    accept_no_brief: bool = False,
    brief_data: dict[str, Any] | None = None,
    in_sequence: bool = False,
) -> dict[str, Any]:
    """Compose read/write/mutate to start a work order.

    Skills should call this directly. If a missing design brief is acceptable
    (the skill has already confirmed with the user), pass `accept_no_brief=True`.

    Pass `in_sequence=True` to abort (exit 1 equivalent: ok=False) when
    earlier-sequence WOs in the same milestone are not yet closed.

    Returns:
        `{"ok": True, "work_order_id": ..., "title": ..., "type": ...,
          "project_id": ..., "context_path": ..., "workflow": {...},
          "next_step": ...}`

    Or on guard failure:
        `{"ok": False, "error": ..., "requires_brief_confirmation": True}` —
        caller must re-call with `accept_no_brief=True` to proceed.
    """

    if brief_data is None:
        # Lazy import (not module-level): keeps `read_work_order_brief` a
        # bare-name call resolved against start_brief's live globals on every
        # invocation, so `patch("core.work_orders.start_brief.read_work_order_brief",
        # ...)` in tests intercepts it — a static top-level import would freeze
        # the reference at start_main import time and silently bypass the patch.
        from .start_brief import read_work_order_brief

        brief_data = read_work_order_brief(
            work_order_id=work_order_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if not brief_data.get("ok"):
        return brief_data

    if brief_data.get("brief_warning") and not accept_no_brief:
        return {
            "ok": False,
            "requires_brief_confirmation": True,
            "error": (
                "No locked design brief found for this UI work order. "
                "Run `website:discover` first, or re-invoke with accept_no_brief=True "
                "(or `--accept-no-brief` on the CLI) to proceed without one."
            ),
            "work_order_id": work_order_id,
        }

    blocking = brief_data.get("blocking_milestone_count", 0)
    if blocking > 0:
        return {
            "ok": False,
            "error": (
                f"Cannot start this work order — {blocking} work order(s) in "
                f"earlier milestones are incomplete. "
                f"Run 'ds project next {brief_data['project_id']}' to see what "
                f"should be worked on first."
            ),
        }

    # Sequence-order check: warn (or abort if in_sequence) when lower-seq WOs
    # in the same milestone are not yet closed.
    # Lazy import (not module-level) — see the `read_work_order_brief` note above;
    # keeps `patch("core.work_orders.start_shared._require_db", ...)` able to
    # intercept every call site below.
    from .start_shared import _require_db

    _db_path_for_seq = _require_db(source_root, dream_studio_home)
    _seq_blockers = _check_sequence_order(work_order_id, _db_path_for_seq)
    if _seq_blockers:
        blocker_lines = "; ".join(
            f"{b['title']} (seq={b['sequence_order']}, id={b['work_order_id']})"
            for b in _seq_blockers
        )
        if in_sequence:
            return {
                "ok": False,
                "error": (
                    f"Out-of-sequence start blocked — {len(_seq_blockers)} earlier WO(s)"
                    f" in this milestone are not closed: {blocker_lines}"
                ),
                "sequence_blockers": _seq_blockers,
            }
        # Soft warning — callers receive the list and can surface it.
        # Execution continues: Proceeding.

    # Preflight gate removed migration 148 (WO-SCHEMALEAN): the
    # business_work_order_preflights stack was unwired (no writer, permanent no-op)
    # and duplicative of the live CI blast-radius gate.

    p_root = planning_root or Path.cwd() / ".planning"
    now = datetime.now(UTC).isoformat()
    # Lazy import (not module-level) — see the `read_work_order_brief` note above;
    # keeps `patch("core.work_orders.start_context.write_work_order_context", ...)`
    # able to intercept this call.
    from .start_context import write_work_order_context

    context_path = write_work_order_context(
        brief_data, planning_root=p_root, now=now, db_path=_db_path_for_seq
    )

    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        envelope = CanonicalEventEnvelope(
            event_type="work_order.started",
            session_id=None,
            payload={
                "work_order_id": work_order_id,
                "title": brief_data["title"],
                "type": brief_data["type_id"],
                "project_id": brief_data["project_id"],
            },
            timestamp=now,
            severity="info",
            trace={
                "domain": "sdlc",
                "work_order_id": work_order_id,
                "milestone_id": brief_data.get("milestone_id"),
                "project_id": brief_data["project_id"],
                "attribution_status": "fully_attributed",
            },
        )
        _spool_writer.write_event(envelope.to_dict())
    except Exception:
        pass

    try:
        _db = _require_db(source_root, dream_studio_home)
        with _connect(_db) as conn:
            conn.execute(
                "UPDATE business_work_orders"
                " SET status = 'in_progress', started_at = ?, updated_at = ?, last_updated_at = ?"
                " WHERE work_order_id = ?",
                (now, now, now, work_order_id),
            )
    except Exception:
        pass

    result: dict[str, Any] = {
        "ok": True,
        "work_order_id": work_order_id,
        "title": brief_data["title"],
        "type": brief_data["type_id"],
        "project_id": brief_data["project_id"],
        # WO-FILESDB-C2: context lives in the authority (kind='context'); context_path
        # is None when stored in the DB (read it via `ds work-order artifact <id> context`),
        # and a .planning path only on the unreleased-migration disk fallback.
        "context_path": str(context_path) if context_path else None,
        "context_in_authority": context_path is None,
    }

    # WO-ESCALATION-LADDER T5: the manual path honors the escalation capability flag.
    # An escalated WO routes its (re)try to a more capable model; surface the resolved
    # executor so the operator/agent runs it there. The autonomous loop honors the same
    # flag via `ds work-order executor` (resolve_executor is the single source of truth).
    try:
        from core.work_orders.escalation import read_escalation, resolve_executor

        _esc_db = _require_db(source_root, dream_studio_home)
        result["executor"] = resolve_executor(work_order_id, db_path=_esc_db)
        _esc_row = read_escalation(work_order_id, db_path=_esc_db)
        if _esc_row and (_esc_row.get("escalation_level") or 0) >= 1:
            result["escalation"] = {
                "level": _esc_row["escalation_level"],
                "designated_executor": _esc_row.get("designated_executor"),
                "retry_count": _esc_row.get("retry_count"),
            }
    except Exception:
        pass

    workflow_template = brief_data.get("workflow_template")
    if workflow_template:
        result["workflow"] = {
            "template": workflow_template,
            "first_node": "think",
            "invoke": f"workflow: {workflow_template}",
        }
        result["next_step"] = (
            f"This work order uses the `{workflow_template}` workflow. "
            f"First node: `think`. Invoke `ds-core:think` to begin."
        )

    # Attach soft sequence warning when lower-seq WOs were detected.
    if _seq_blockers:
        blocker_lines = "; ".join(
            f"{b['title']} (seq={b['sequence_order']}, id={b['work_order_id']})"
            for b in _seq_blockers
        )
        result["sequence_warning"] = (
            f"WARNING: {len(_seq_blockers)} earlier WO(s) in this milestone are not closed:"
            f" {blocker_lines}. Proceeding."
        )
        result["sequence_blockers"] = _seq_blockers

    # pending_audits feature retired (migration 131): writer defer_project_audit()
    # was dead, table dropped. The advisory reader is removed with it.

    return result
