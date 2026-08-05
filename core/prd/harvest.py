"""P3: evidence harvesters for the PRD+SOW rescore engine (WO 4d495283 / SPEC-0001 R4-R5).

Reads only existing authority + docstore state — per-WO verify composites, and the milestone
gate artifacts (design-audit / security-audit / harden-results). Never re-runs workflows;
never fabricates a missing signal (an absent signal is simply omitted, lowering confidence).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

CAPABILITY_MAP_NAME = "prd/capability-map.yaml"


def read_capability_map(*, db_path: Path | None = None) -> dict[str, Any]:
    """Load the PRD capability map from the docstore (files.db).

    Returns a dict with keys ``capabilities`` (list of {capability_id, title, weight}),
    ``milestone_capabilities`` ({milestone_id: [capability_id, ...]}), and an optional
    ``milestone_accomplished`` ({milestone_id: operator-authored text}). Missing map → empty.
    """
    import yaml

    from core.files.store import read_file_by_name

    try:
        row = read_file_by_name(CAPABILITY_MAP_NAME, db_path=db_path)
    except KeyError:
        row = None
    if row is None:
        return {"capabilities": [], "milestone_capabilities": {}, "milestone_accomplished": {}}
    content = row["content"]
    if isinstance(content, (bytes, bytearray)):
        content = content.decode("utf-8")
    data = yaml.safe_load(content) or {}
    data.setdefault("capabilities", [])
    data.setdefault("milestone_capabilities", {})
    data.setdefault("milestone_accomplished", {})
    return data


def _milestone_artifact(
    planning_root: Path, milestone_id: str, filename: str, files_db_path: Path | None
) -> str | None:
    from core.milestones.artifacts import read_milestone_artifact

    return read_milestone_artifact(
        planning_root / "milestones" / milestone_id, filename, db_path=files_db_path
    )


def harvest_milestone(
    conn: Any, milestone_id: str, planning_root: Path, *, files_db_path: Path | None = None
) -> dict[str, Any]:
    """Gather a milestone's real evidence signals from the authority + docstore.

    Signals (each 0-100, or None when absent):
      - wo_composites: each work order's verify_score (0-1) x100
      - design_score:   design-audit ``Score: N/M`` -> N/M x100
      - security_score: security-audit -> 0 if it contains BLOCKED else 100
      - harden_score:   harden-results -> 100 if it contains PASSED else 0
    """
    wo_rows = conn.execute(
        "SELECT work_order_id, title, status, verify_score FROM business_work_orders"
        " WHERE milestone_id = ? ORDER BY created_at",
        (milestone_id,),
    ).fetchall()
    closed_titles = [r[1] for r in wo_rows if r[2] == "closed"]
    wo_composites = [float(r[3]) * 100.0 for r in wo_rows if r[3] is not None]

    design = _milestone_artifact(planning_root, milestone_id, "design-audit.md", files_db_path)
    security = _milestone_artifact(planning_root, milestone_id, "security-audit.md", files_db_path)
    harden = _milestone_artifact(planning_root, milestone_id, "harden-results.md", files_db_path)

    design_score: float | None = None
    if design:
        m = re.search(r"Score:\s*(\d+)/(\d+)", design)
        if m and int(m.group(2)):
            design_score = int(m.group(1)) / int(m.group(2)) * 100.0
    security_score = None if security is None else (0.0 if "BLOCKED" in security.upper() else 100.0)
    harden_score = None if harden is None else (100.0 if "PASSED" in harden.upper() else 0.0)

    return {
        "work_order_count": len(wo_rows),
        "closed_titles": closed_titles,
        "wo_composites": wo_composites,
        "design_score": design_score,
        "security_score": security_score,
        "harden_score": harden_score,
    }


def milestone_signals(ev: dict[str, Any]) -> list[float]:
    """The available 0-100 evidence signals for a milestone (absent signals omitted)."""
    signals = list(ev["wo_composites"])
    for key in ("design_score", "security_score", "harden_score"):
        if ev[key] is not None:
            signals.append(ev[key])
    return signals
