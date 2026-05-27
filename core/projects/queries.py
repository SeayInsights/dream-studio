"""Read-only project queries.

Skills, workflows, and hooks should import these directly instead of
shelling out to `ds project list`, `ds project status`, `ds project next`,
or `ds project state`. Each function returns a dict; the CLI wrapper in
`interfaces/cli/ds.py` is responsible for serialization.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect


def _require_db(source_root: Path, dream_studio_home: Path | None) -> Path:
    # Lazy import via `interfaces.cli.ds` so tests that patch
    # `interfaces.cli.ds.resolve_installed_runtime_paths` flow through to
    # callers in `core.*` without breaking the architectural direction at
    # import time. `interfaces.cli.ds` re-exports the function from
    # `core.installed_runtime`, so this is a re-route, not a new dependency.
    from interfaces.cli.ds import resolve_installed_runtime_paths

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing. Run rehearsal-install first.")
    return paths.sqlite_path


def get_project_list(
    *,
    status_filter: str = "active",
    include_deleted: bool = False,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    db_path = _require_db(source_root, dream_studio_home)
    with _connect(db_path) as conn:
        if include_deleted:
            rows = conn.execute(
                "SELECT project_id, name, description, status, created_at FROM business_projects"
                " ORDER BY created_at DESC",
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT project_id, name, description, status, created_at FROM business_projects"
                " WHERE status = ? ORDER BY created_at DESC",
                (status_filter,),
            ).fetchall()
    projects = [
        {
            "project_id": r[0],
            "name": r[1],
            "description": r[2],
            "status": r[3],
            "created_at": r[4],
        }
        for r in rows
    ]
    return {"ok": True, "projects": projects}


def get_project_status(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    db_path = _require_db(source_root, dream_studio_home)
    with _connect(db_path) as conn:
        proj = conn.execute(
            "SELECT project_id, name, status FROM business_projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if proj is None:
            return {"ok": False, "error": f"Project not found: {project_id}"}
        milestone_count = conn.execute(
            "SELECT COUNT(*) FROM business_milestones WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]
        work_order_count = conn.execute(
            "SELECT COUNT(*) FROM business_work_orders WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]
        open_work_order_count = conn.execute(
            "SELECT COUNT(*) FROM business_work_orders WHERE project_id = ? AND status = 'created'",
            (project_id,),
        ).fetchone()[0]
    return {
        "ok": True,
        "project_id": proj[0],
        "name": proj[1],
        "status": proj[2],
        "milestone_count": milestone_count,
        "work_order_count": work_order_count,
        "open_work_order_count": open_work_order_count,
    }


def get_next_work_order(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    db_path = _require_db(source_root, dream_studio_home)
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT wo.work_order_id, wo.title, wo.work_order_type, m.title AS milestone_title"
            " FROM business_work_orders wo"
            " LEFT JOIN business_milestones m ON wo.milestone_id = m.milestone_id"
            " WHERE wo.project_id = ? AND wo.status = 'in_progress'"
            " ORDER BY m.order_index ASC, wo.created_at ASC LIMIT 1",
            (project_id,),
        ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT wo.work_order_id, wo.title, wo.work_order_type, m.title AS milestone_title"
                " FROM business_work_orders wo"
                " LEFT JOIN business_milestones m ON wo.milestone_id = m.milestone_id"
                " WHERE wo.project_id = ? AND wo.status = 'created'"
                " AND m.order_index = ("
                "   SELECT MIN(m2.order_index)"
                "   FROM business_work_orders wo2"
                "   LEFT JOIN business_milestones m2 ON wo2.milestone_id = m2.milestone_id"
                "   WHERE wo2.project_id = ? AND wo2.status IN ('created', 'in_progress')"
                " )"
                " ORDER BY wo.created_at ASC LIMIT 1",
                (project_id, project_id),
            ).fetchone()
    if row is None:
        return {"ok": True, "work_order": None, "message": "No open work orders"}
    wo_id = row[0]
    return {
        "ok": True,
        "work_order": {
            "work_order_id": wo_id,
            "title": row[1],
            "work_order_type": row[2],
            "milestone": row[3] or "",
            "next_command": f"ds work-order start {wo_id}",
        },
    }


def get_project_state(
    *,
    source_root: Path,
    dream_studio_home: Path | None = None,
    planning_root: Path | None = None,
) -> dict[str, Any]:
    """Single-call project state — active project + next WO + gates + brief + tasks + gotchas."""

    from core.work_orders.close import run_gate_check

    db_path = _require_db(source_root, dream_studio_home)
    p_root = planning_root or Path.cwd() / ".planning"

    with _connect(db_path) as conn:
        projects_raw = conn.execute(
            "SELECT project_id, name, status FROM business_projects WHERE status = 'active'"
            " ORDER BY updated_at DESC"
        ).fetchall()

        if not projects_raw:
            return {
                "ok": True,
                "projects": [],
                "next_action": "No active projects. Run `ds-project scope` to scope a new one.",
            }

        result_projects: list[dict[str, Any]] = []
        for proj in projects_raw:
            pid = proj["project_id"]

            wo_row = conn.execute(
                "SELECT wo.work_order_id, wo.title, wo.status, wo.work_order_type,"
                " m.milestone_id, m.title AS milestone_title, m.order_index,"
                " wot.label, wot.pre_build_gate, wot.build_executor, wot.post_build_gate,"
                " wot.workflow_template, wot.precondition_skill, wot.task_generator,"
                " (SELECT COUNT(*) FROM business_tasks t"
                "  WHERE t.work_order_id = wo.work_order_id AND t.status = 'pending') AS pending_tasks,"
                " (SELECT COUNT(*) FROM business_tasks t"
                "  WHERE t.work_order_id = wo.work_order_id) AS total_tasks"
                " FROM business_work_orders wo"
                " LEFT JOIN business_milestones m ON wo.milestone_id = m.milestone_id"
                " LEFT JOIN business_work_order_types wot ON wot.type_id = wo.work_order_type"
                " WHERE wo.project_id = ? AND wo.status IN ('created', 'in_progress')"
                " ORDER BY m.order_index ASC, wo.created_at ASC LIMIT 1",
                (pid,),
            ).fetchone()

            brief_row = None
            try:
                brief_row = conn.execute(
                    "SELECT brief_id, status, purpose, audience, tone, design_system,"
                    " font_pairing, brand_tokens FROM business_design_briefs"
                    " WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
                    (pid,),
                ).fetchone()
            except Exception:
                pass

            brief_info: dict[str, Any] | None = None
            if brief_row:
                fields = [
                    "purpose",
                    "audience",
                    "tone",
                    "design_system",
                    "font_pairing",
                    "brand_tokens",
                ]
                filled = sum(1 for f in fields if brief_row[f])
                brief_info = {
                    "brief_id": brief_row["brief_id"],
                    "status": brief_row["status"],
                    "fields_filled": filled,
                    "fields_total": len(fields),
                }

            wo_info: dict[str, Any] | None = None
            next_action = "No open work orders. All milestones may be complete."

            if wo_row:
                wo_type = wo_row["work_order_type"]
                build_exec = wo_row["build_executor"]
                pre_gate = wo_row["pre_build_gate"]
                precondition_skill = wo_row["precondition_skill"]
                workflow_template = wo_row["workflow_template"]
                task_generator = wo_row["task_generator"] or "ds-core:plan"

                gate_satisfied = True
                if pre_gate:
                    gate_passed, _ = run_gate_check(
                        pre_gate,
                        planning_root=p_root,
                        work_order_id=wo_row["work_order_id"],
                        project_id=pid,
                        conn=conn,
                    )
                    gate_satisfied = gate_passed

                gotcha_rows: list[Any] = []
                try:
                    gotcha_rows = conn.execute(
                        "SELECT severity, title, fix FROM reg_gotchas"
                        " WHERE skill_id = ? OR skill_id LIKE ?"
                        " ORDER BY times_hit DESC, discovered DESC LIMIT 3",
                        (build_exec or "", f"{wo_type}%" if wo_type else ""),
                    ).fetchall()
                except Exception:
                    pass

                gotchas = [
                    {"severity": g["severity"], "title": g["title"], "fix": g["fix"]}
                    for g in gotcha_rows
                ]

                if not gate_satisfied and pre_gate:
                    skill_hint = precondition_skill or "ds-project:brief"
                    next_action = (
                        f"Gate `{pre_gate}` is not satisfied. "
                        f"Invoke `{skill_hint}` to resolve it."
                    )
                elif wo_row["total_tasks"] == 0:
                    next_action = (
                        f"No tasks defined for this work order. "
                        f"Invoke `{task_generator}` to decompose tasks, "
                        f"then `ds work-order start {wo_row['work_order_id']}`."
                    )
                elif wo_row["status"] == "created":
                    next_action = f"Run: ds work-order start {wo_row['work_order_id']}"
                    if workflow_template:
                        next_action += (
                            f"\nWorkflow: `{workflow_template}`. "
                            f"First node: `think`. Invoke `ds-core:think` to begin."
                        )
                else:
                    next_action = (
                        f"Work order in progress. Complete remaining tasks, "
                        f"then: ds work-order close {wo_row['work_order_id']}"
                    )

                wo_info = {
                    "work_order_id": wo_row["work_order_id"],
                    "title": wo_row["title"],
                    "status": wo_row["status"],
                    "type": wo_type,
                    "type_label": wo_row["label"],
                    "workflow_template": workflow_template,
                    "pending_tasks": wo_row["pending_tasks"],
                    "total_tasks": wo_row["total_tasks"],
                    "gates": {
                        "pre_build": pre_gate,
                        "pre_build_satisfied": gate_satisfied,
                        "precondition_skill": precondition_skill,
                        "build_executor": build_exec,
                        "post_build": wo_row["post_build_gate"],
                    },
                    "design_brief": brief_info,
                    "milestone": {
                        "milestone_id": wo_row["milestone_id"],
                        "title": wo_row["milestone_title"],
                        "order_index": wo_row["order_index"],
                    },
                    "gotchas": gotchas,
                }

            result_projects.append(
                {
                    "project_id": pid,
                    "name": proj["name"],
                    "status": proj["status"],
                    "next_work_order": wo_info,
                    "next_action": next_action,
                }
            )

    return {"ok": True, "projects": result_projects}
