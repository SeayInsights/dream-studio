"""Shared DB/artifact plumbing for work-order close.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/close.py``. Holds the
authority-DB path resolution, the artifact-text lookup (authority table first,
``.planning`` disk fallback), and the WO-row + gate-columns lookup shared by
the gate-check and main-close siblings. No logic changes — extracted
verbatim from the original module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _require_db(source_root: Path, dream_studio_home: Path | None) -> Path:
    # Lazy import via ds.py — see core.work_orders.start._require_db for rationale.
    from interfaces.cli.ds import resolve_installed_runtime_paths

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing. Run rehearsal-install first.")
    return paths.sqlite_path


def _artifact_text(work_order_id: str, wo_dir: Path, kind: str, db_path: Path | None) -> str | None:
    """WO ceremony artifact content — authority table first, .planning disk fallback.

    WO-FILESDB-P1: artifacts moved into business_work_order_artifacts. The disk
    fallback keeps historical WOs (and the live authority DB before the migration
    is activated) gate-satisfiable during the transition.
    """
    from core.work_orders.artifacts import KIND_TO_FILENAME, get_wo_artifact

    content = get_wo_artifact(work_order_id, kind, db_path=db_path)
    if content is not None:
        return content
    fpath = wo_dir / KIND_TO_FILENAME[kind]
    if fpath.is_file():
        return fpath.read_text(encoding="utf-8")
    return None


def _lookup_work_order_and_gates(conn: Any, work_order_id: str) -> dict[str, Any]:
    """Internal helper: read WO row + type row, return everything close needs.

    Returns either ``{"ok": False, "error": ...}`` or a dict with keys:
    ``work_order_id, title, wo_status, type_id, project_id, milestone_id,
    pre_gate, post_gate, originating_symptom``.
    """

    wo_row = conn.execute(
        "SELECT work_order_id, title, status, work_order_type, project_id,"
        " milestone_id, originating_symptom"
        " FROM business_work_orders WHERE work_order_id = ?",
        (work_order_id,),
    ).fetchone()
    if wo_row is None:
        return {"ok": False, "error": f"Work order not found: {work_order_id}"}

    wo_id, title, wo_status, wo_type, project_id, milestone_id, orig_symptom = wo_row

    pre_gate = None
    post_gate = None
    if wo_type:
        type_row = conn.execute(
            "SELECT pre_build_gate, build_executor, post_build_gate"
            " FROM business_work_order_types WHERE type_id = ?",
            (wo_type,),
        ).fetchone()
        if type_row is not None:
            pre_gate = type_row[0]
            post_gate = type_row[2]

    return {
        "ok": True,
        "work_order_id": wo_id,
        "title": title,
        "wo_status": wo_status,
        "type_id": wo_type,
        "project_id": project_id,
        "milestone_id": milestone_id,
        "pre_gate": pre_gate,
        "post_gate": post_gate,
        "originating_symptom": orig_symptom,
    }
