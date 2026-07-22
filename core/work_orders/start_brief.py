"""Work-order brief reader for work-order start.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/start.py``. Holds
``read_work_order_brief`` — everything needed to decide whether a work order
can start (type/gate metadata, milestone/project context, pending tasks,
locked design brief, gotchas, blocking-milestone count). No logic changes —
extracted verbatim from the original module.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect

from .start_shared import _UI_WO_TYPES


def read_work_order_brief(
    *,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Read everything needed to decide whether a work order can start.

    Returns a dict shaped like:

        {
            "ok": True | False,
            "error": str (when ok=False),
            # When ok=True:
            "work_order_id": str,
            "title": str,
            "status": str,
            "type_id": str,
            "label": str,
            "pre_gate": str | None,
            "build_exec": str | None,
            "post_gate": str | None,
            "workflow_template": str | None,
            "precondition_skill": str | None,
            "milestone_id": str | None,
            "milestone_title": str | None,
            "project_id": str,
            "project_name": str,
            "marker_project_id": str | None,
            "pending_tasks": list[{"title": str}],
            "brief_locked": dict | None,   # locked brief fields if UI type
            "brief_warning": bool,          # True if UI type and no locked brief
            "gotchas": list[{"severity", "title", "fix"}],
            "blocking_milestone_count": int,  # earlier-milestone incomplete WOs
        }
    """

    # Lazy import (not module-level): keeps `_require_db` a bare-name call
    # resolved against start_shared's live globals on every invocation, so
    # `patch("core.work_orders.start_shared._require_db", ...)` in tests
    # intercepts it. A static top-level import would risk binding a frozen
    # snapshot the first time this module is ever imported — if that happens
    # while some unrelated test's patch of `start_shared._require_db` is
    # active (e.g. while `unittest.mock.patch` resolves a sibling string
    # target and triggers this module's first import as a side effect), the
    # stale reference would silently outlive that test.
    from .start_shared import _require_db

    db_path = _require_db(source_root, dream_studio_home)
    with _connect(db_path) as conn:
        wo_row = conn.execute(
            "SELECT work_order_id, title, status, work_order_type, milestone_id, project_id"
            " FROM business_work_orders WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if wo_row is None:
            return {"ok": False, "error": f"Work order not found: {work_order_id}"}

        wo_id, title, wo_status, wo_type, milestone_id, project_id = wo_row

        if not wo_type:
            return {"ok": False, "error": "Work order has no type assigned"}

        type_row = conn.execute(
            "SELECT type_id, label, pre_build_gate, build_executor, post_build_gate,"
            " workflow_template, precondition_skill"
            " FROM business_work_order_types WHERE type_id = ?",
            (wo_type,),
        ).fetchone()
        if type_row is None:
            return {"ok": False, "error": f"Unrecognized work order type: {wo_type}"}

        (
            type_id,
            label,
            pre_gate,
            build_exec,
            post_gate,
            workflow_template,
            precondition_skill,
        ) = type_row

        milestone_title = None
        if milestone_id:
            ms_row = conn.execute(
                "SELECT title FROM business_milestones WHERE milestone_id = ?",
                (milestone_id,),
            ).fetchone()
            milestone_title = ms_row[0] if ms_row else None

        proj_row = conn.execute(
            "SELECT name FROM business_projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        project_name = proj_row[0] if proj_row else project_id

        open_tasks = conn.execute(
            "SELECT title FROM business_tasks"
            " WHERE work_order_id = ? AND status = 'pending' ORDER BY created_at ASC",
            (work_order_id,),
        ).fetchall()
        pending_tasks = [{"title": row[0]} for row in open_tasks]

        brief_locked: dict[str, Any] | None = None
        brief_warning = False
        if type_id in _UI_WO_TYPES and project_id:
            try:
                b_row = conn.execute(
                    "SELECT brief_id, purpose, audience, tone, design_system,"
                    " font_pairing, brand_tokens, status"
                    " FROM business_design_briefs"
                    " WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
                    (project_id,),
                ).fetchone()
                if b_row and b_row[7] == "locked":
                    brief_locked = {
                        "brief_id": b_row[0],
                        "purpose": b_row[1],
                        "audience": b_row[2],
                        "tone": b_row[3],
                        "design_system": b_row[4],
                        "font_pairing": b_row[5],
                        "brand_tokens": b_row[6],
                    }
                else:
                    brief_warning = True
            except sqlite3.OperationalError:
                brief_warning = True

        marker_project_id: str | None = None
        try:
            from emitters.claude_code.project import read_project_id

            marker_project_id = read_project_id(source_root)
        except Exception:
            pass

        gotchas: list[dict[str, Any]] = []
        try:
            gotcha_rows = conn.execute(
                "SELECT severity, title, fix FROM reg_gotchas"
                " WHERE skill_id = ? OR skill_id LIKE ?"
                " ORDER BY times_hit DESC, discovered DESC LIMIT 3",
                (build_exec or "", f"{type_id}%" if type_id else ""),
            ).fetchall()
            gotchas = [{"severity": g[0], "title": g[1], "fix": g[2]} for g in gotcha_rows]
        except Exception:
            pass

        blocking_milestone_count = 0
        if milestone_id:
            ms_order_row = conn.execute(
                "SELECT order_index FROM business_milestones WHERE milestone_id = ?",
                (milestone_id,),
            ).fetchone()
            if ms_order_row is not None:
                blocking_milestone_count = conn.execute(
                    "SELECT COUNT(*) FROM business_work_orders wo"
                    " LEFT JOIN business_milestones m ON wo.milestone_id = m.milestone_id"
                    " WHERE wo.project_id = ? AND m.order_index < ?"
                    " AND wo.status NOT IN ('closed', 'cancelled')",
                    (project_id, ms_order_row[0]),
                ).fetchone()[0]

    return {
        "ok": True,
        "work_order_id": wo_id,
        "title": title,
        "status": wo_status,
        "type_id": type_id,
        "label": label,
        "pre_gate": pre_gate,
        "build_exec": build_exec,
        "post_gate": post_gate,
        "workflow_template": workflow_template,
        "precondition_skill": precondition_skill,
        "milestone_id": milestone_id,
        "milestone_title": milestone_title,
        "project_id": project_id,
        "project_name": project_name,
        "marker_project_id": marker_project_id,
        "pending_tasks": pending_tasks,
        "brief_locked": brief_locked,
        "brief_warning": brief_warning,
        "gotchas": gotchas,
        "blocking_milestone_count": blocking_milestone_count,
    }
