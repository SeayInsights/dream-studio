"""Dashboard PRD+SOW panel read-model (WO P5).

A READ-ONLY projection of the derived PRD + Statement-of-Work view for the dashboard: the
overall score, per-capability coverage, and per-milestone SOW entries. It calls the engine's
no-write ``compute_prd_sow`` (never ``rescore_prd``) so rendering the dashboard cannot mutate
the docstore. Read-only over the authority; adds no new authority and no studio.db table.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

PANEL_SCHEMA = "dream_studio.prd_sow.panel.v1"


def build_prd_sow_panel(
    project_id: str,
    *,
    source_root: Path | None = None,
    dream_studio_home: Path | None = None,
    db_path: Path | None = None,
    files_db_path: Path | None = None,
) -> dict[str, Any]:
    """Return the PRD+SOW panel shape for a project, derived read-only.

    Shape::

        {schema, project_id, overall_score, coverage, confidence,
         capabilities: [{capability_id, title, score, status, weight, milestone_ids}],
         milestones:   [{milestone_id, title, set_out_to, accomplished, score, status,
                         confidence, capabilities}]}
    """
    from core.prd.rescore import compute_prd_sow

    result = compute_prd_sow(
        project_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        db_path=db_path,
        files_db_path=files_db_path,
    )
    if not result.get("ok"):
        return {
            "schema": PANEL_SCHEMA,
            "project_id": project_id,
            "ok": False,
            "overall_score": 0.0,
            "coverage": 0.0,
            "confidence": 0.0,
            "capabilities": [],
            "milestones": [],
        }
    return {
        "schema": PANEL_SCHEMA,
        "project_id": project_id,
        "ok": True,
        "overall_score": result["overall_score"],
        "coverage": result["coverage"],
        "confidence": result["confidence"],
        "capabilities": result["capabilities"],
        "milestones": result["milestones"],
    }
