"""Work-order start: read brief, write context.md, mutate to in_progress.

This module replaces the monolithic `_work_order_start` handler that lived in
`interfaces/cli/ds.py`. It decomposes the work into three pure functions so
skills, workflows, and hooks can compose them directly without going through
the CLI subprocess:

- `read_work_order_brief(work_order_id=, source_root=, dream_studio_home=)`
    Reads work order, type, milestone, project, pending tasks, design brief,
    gotchas, marker project id, and blocking-milestone count. Returns a
    fully-structured dict with everything needed to render the context.md and
    decide whether the start is allowed.

- `write_work_order_context(brief_data, planning_root, now)`
    Pure markdown generator. Takes the dict from `read_work_order_brief` and
    writes `<planning_root>/work-orders/<wo_id>/context.md`. Returns the
    written path.

- `start_work_order(work_order_id=, accept_no_brief=False, source_root=,
                    dream_studio_home=, planning_root=, brief_data=None)`
    Composer. Reads (or accepts pre-read) brief data, enforces the
    no-brief-for-UI guard via `accept_no_brief`, enforces the
    milestone-ordering guard, writes context.md, updates the row to
    in_progress, emits the `work_order.started` spool event, and returns a
    result dict (with workflow info if the type declares one).

The stdin y/N prompt that used to live in the CLI handler is REMOVED from
the pure path. Skills/operators are expected to confirm before calling
`start_work_order(accept_no_brief=True)`. The CLI wrapper in `ds.py`
preserves the legacy behaviour (warning to stderr, non-TTY auto-accepts)
for backward compat with operator terminals.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect

_UI_WO_TYPES: frozenset[str] = frozenset({"ui_component", "ui_page"})


def _require_db(source_root: Path, dream_studio_home: Path | None) -> Path:
    # Lazy import via ds.py — see core.projects.queries._require_db for rationale.
    from interfaces.cli.ds import resolve_installed_runtime_paths

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing. Run rehearsal-install first.")
    return paths.sqlite_path


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

    db_path = _require_db(source_root, dream_studio_home)
    with _connect(db_path) as conn:
        wo_row = conn.execute(
            "SELECT work_order_id, title, status, work_order_type, milestone_id, project_id"
            " FROM ds_work_orders WHERE work_order_id = ?",
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
            " FROM ds_work_order_types WHERE type_id = ?",
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
                "SELECT title FROM ds_milestones WHERE milestone_id = ?",
                (milestone_id,),
            ).fetchone()
            milestone_title = ms_row[0] if ms_row else None

        proj_row = conn.execute(
            "SELECT name FROM ds_projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        project_name = proj_row[0] if proj_row else project_id

        open_tasks = conn.execute(
            "SELECT title FROM ds_tasks"
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
                    " FROM ds_design_briefs"
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
                "SELECT order_index FROM ds_milestones WHERE milestone_id = ?",
                (milestone_id,),
            ).fetchone()
            if ms_order_row is not None:
                blocking_milestone_count = conn.execute(
                    "SELECT COUNT(*) FROM ds_work_orders wo"
                    " LEFT JOIN ds_milestones m ON wo.milestone_id = m.milestone_id"
                    " WHERE wo.project_id = ? AND m.order_index < ?"
                    " AND wo.status NOT IN ('complete', 'cancelled')",
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


def write_work_order_context(
    brief_data: dict[str, Any],
    *,
    planning_root: Path,
    now: str | None = None,
) -> Path:
    """Pure markdown generator + file write.

    Takes the dict returned by `read_work_order_brief` and writes
    `<planning_root>/work-orders/<wo_id>/context.md`. Returns the path.
    """

    if not brief_data.get("ok"):
        raise ValueError(
            "write_work_order_context requires an ok=True brief_data dict; " f"got {brief_data}"
        )

    now = now or datetime.now(timezone.utc).isoformat()
    work_order_id = brief_data["work_order_id"]
    title = brief_data["title"]
    type_id = brief_data["type_id"]
    label = brief_data["label"]
    wo_status = brief_data["status"]
    project_id = brief_data["project_id"]
    project_name = brief_data["project_name"]
    milestone_title = brief_data.get("milestone_title")
    marker_project_id = brief_data.get("marker_project_id")
    pre_gate = brief_data.get("pre_gate")
    build_exec = brief_data.get("build_exec")
    post_gate = brief_data.get("post_gate")
    workflow_template = brief_data.get("workflow_template")
    pending_tasks = brief_data.get("pending_tasks") or []
    brief_locked = brief_data.get("brief_locked")
    brief_warning = brief_data.get("brief_warning", False)
    gotchas = brief_data.get("gotchas") or []

    context_dir = planning_root / "work-orders" / work_order_id
    context_dir.mkdir(parents=True, exist_ok=True)
    context_path = context_dir / "context.md"

    lines = [
        f"# Work Order: {title}",
        "",
        f"**ID:** `{work_order_id}`",
        f"**Type:** {label} (`{type_id}`)",
        f"**Status:** {wo_status}",
        f"**Project:** {project_name} (`{project_id}`)",
    ]
    if milestone_title:
        lines.append(f"**Milestone:** {milestone_title}")
    if marker_project_id:
        lines.append(f"**Active project (marker):** `{marker_project_id}`")
    lines += [
        "",
        "## Gates",
        "",
        f"- **Pre-build gate:** {pre_gate or '—'}",
        f"- **Build executor:** {build_exec or '—'}",
        f"- **Post-build gate:** {post_gate or '—'}",
    ]
    if workflow_template:
        lines.append(f"- **Workflow:** {workflow_template} — invoke `ds-core:think` to begin")
    lines += [
        "",
        "## Open Tasks",
        "",
    ]
    if pending_tasks:
        for task in pending_tasks:
            lines.append(f"- [ ] {task['title']}")
    else:
        lines.append("_No pending tasks._")

    if brief_locked:
        lines += ["", "## Design Brief", ""]
        for _lbl, _key in [
            ("Purpose", "purpose"),
            ("Audience", "audience"),
            ("Tone", "tone"),
            ("Font pairing", "font_pairing"),
            ("Brand tokens", "brand_tokens"),
        ]:
            _val = brief_locked.get(_key)
            if _val:
                lines.append(f"- **{_lbl}:** {_val}")
        if brief_locked.get("design_system"):
            _ds = brief_locked["design_system"]
            lines += [
                "",
                "## Design System",
                "",
                f"System: {_ds}",
                f"Reference: canonical/skills/domains/design-systems/{_ds}/",
                "",
                "Apply the principles from this design system to all UI output in this"
                " work order. Do not deviate from the system's token definitions.",
            ]
    elif brief_warning:
        lines += [
            "",
            "> **WARNING:** No locked design brief found."
            " Run `website:discover` before building UI for consistent results.",
        ]

    lines += [
        "",
        "## DREAM STUDIO ENFORCEMENT",
        "",
        "You are operating in Dream Studio managed mode.",
        "This is a hard boundary, not a suggestion.",
        "",
        f"AUTHORIZED scope: {type_id}",
        f"ACTIVE work order: {work_order_id}",
        "AUTHORIZED tasks: listed above under ## Tasks",
        "",
        "RULES:",
        "1. Do not create or modify files outside the authorized scope above.",
        "2. Complete tasks in the order listed.",
        "3. Mark each task done:",
        f"   py -m interfaces.cli.ds work-order task-done {work_order_id} <task_id>",
        "4. When all tasks are complete, run:",
        f"   py -m interfaces.cli.ds work-order close {work_order_id}",
        "5. Do not start work on any other work order until this one is closed.",
        "6. If you encounter something outside your scope that needs to be addressed,",
        "   emit a note and continue. Do not fix it inline.",
        "",
        "Violations of these rules break traceability.",
        "Dream Studio exists to make your work verifiable.",
    ]

    if gotchas:
        lines += ["", "## Known Issues (from past sessions)", ""]
        for g in gotchas:
            lines.append(f"- **[{g['severity']}]** {g['title']}")
            if g.get("fix"):
                lines.append(f"  Fix: {g['fix']}")

    lines += ["", f"_Generated: {now}_", ""]
    context_path.write_text("\n".join(lines), encoding="utf-8")
    return context_path


def start_work_order(
    *,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
    planning_root: Path | None = None,
    accept_no_brief: bool = False,
    brief_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose read/write/mutate to start a work order.

    Skills should call this directly. If a missing design brief is acceptable
    (the skill has already confirmed with the user), pass `accept_no_brief=True`.

    Returns:
        `{"ok": True, "work_order_id": ..., "title": ..., "type": ...,
          "project_id": ..., "context_path": ..., "workflow": {...},
          "next_step": ...}`

    Or on guard failure:
        `{"ok": False, "error": ..., "requires_brief_confirmation": True}` —
        caller must re-call with `accept_no_brief=True` to proceed.
    """

    if brief_data is None:
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

    p_root = planning_root or Path.cwd() / ".planning"
    now = datetime.now(timezone.utc).isoformat()
    context_path = write_work_order_context(brief_data, planning_root=p_root, now=now)

    db_path = _require_db(source_root, dream_studio_home)
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE ds_work_orders SET status = 'in_progress', updated_at = ?"
            " WHERE work_order_id = ?",
            (now, work_order_id),
        )
        conn.commit()

    try:
        import spool.writer as _spool_writer

        _spool_writer.write_event(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "work_order.started",
                "timestamp": now,
                "trace": {
                    "work_order_id": work_order_id,
                    "project_id": brief_data["project_id"],
                },
                "severity": "info",
                "payload": {
                    "work_order_id": work_order_id,
                    "title": brief_data["title"],
                    "type": brief_data["type_id"],
                    "project_id": brief_data["project_id"],
                },
                "source_type": "confirmed",
            }
        )
    except Exception:
        pass

    result: dict[str, Any] = {
        "ok": True,
        "work_order_id": work_order_id,
        "title": brief_data["title"],
        "type": brief_data["type_id"],
        "project_id": brief_data["project_id"],
        "context_path": str(context_path),
    }
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
    return result
