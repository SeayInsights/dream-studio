"""Read-only milestone queries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect


def _require_db(source_root: Path, dream_studio_home: Path | None) -> Path:
    # Lazy import via ds.py — see core.projects.queries._require_db for rationale.
    from interfaces.cli.ds import resolve_installed_runtime_paths

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing.")
    return paths.sqlite_path


def list_milestones(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    db_path = _require_db(source_root, dream_studio_home)
    with _connect(db_path) as conn:
        ms_rows = conn.execute(
            "SELECT milestone_id, title, status FROM business_milestones"
            " WHERE project_id = ? ORDER BY created_at ASC",
            (project_id,),
        ).fetchall()
        milestones: list[dict[str, Any]] = []
        for ms_id, title, status in ms_rows:
            wo_count = conn.execute(
                "SELECT COUNT(*) FROM business_work_orders WHERE milestone_id = ?",
                (ms_id,),
            ).fetchone()[0]
            milestones.append(
                {
                    "milestone_id": ms_id[:8],
                    "milestone_id_full": ms_id,
                    "title": title,
                    "status": status,
                    "work_order_count": wo_count,
                    "depends_on": None,
                }
            )
    return {"ok": True, "milestones": milestones}


def get_milestone_status(
    *,
    milestone_id: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
    planning_root: Path | None = None,
) -> dict[str, Any]:
    db_path = _require_db(source_root, dream_studio_home)
    p_root = planning_root or Path.cwd() / ".planning"
    ms_dir = p_root / "milestones" / milestone_id

    with _connect(db_path) as conn:
        ms_row = conn.execute(
            "SELECT milestone_id, project_id, title, status, due_date FROM business_milestones"
            " WHERE milestone_id = ?",
            (milestone_id,),
        ).fetchone()
        if ms_row is None:
            return {"ok": False, "error": f"Milestone not found: {milestone_id}"}

        ms_id, project_id, title, status, due_date = ms_row

        wo_rows = conn.execute(
            "SELECT work_order_id, title, status, work_order_type FROM business_work_orders"
            " WHERE milestone_id = ? ORDER BY created_at ASC",
            (milestone_id,),
        ).fetchall()

    ui_types = frozenset(["ui_component", "ui_page"])
    has_ui = any(r[3] in ui_types for r in wo_rows)

    from core.milestones.artifacts import read_milestone_artifact

    open_checks: list[str] = []
    for filename, label in [
        ("design-audit.md", "design_audit"),
        ("security-audit.md", "security_audit"),
        ("harden-results.md", "harden_results"),
    ]:
        if read_milestone_artifact(ms_dir, filename) is None:
            open_checks.append(label)
    if has_ui and read_milestone_artifact(ms_dir, "cwv-results.md") is None:
        open_checks.append("cwv_results")

    return {
        "ok": True,
        "milestone_id": ms_id,
        "project_id": project_id,
        "title": title,
        "status": status,
        "due_date": due_date,
        "work_orders": [
            {"work_order_id": r[0], "title": r[1], "status": r[2], "type": r[3]} for r in wo_rows
        ],
        "open_gate_checks": open_checks,
    }
