"""P3: the PRD + Statement-of-Work rescore engine (WO 4d495283 / SPEC-0001 R6-R10).

Pure, idempotent derive-from-authority score + living document. No new studio.db tables; the
rendered PRD+SOW document is written to the files.db docstore as ``prd/prd-sow.md``. Two calls
with no intervening authority change produce identical output apart from the refresh timestamp.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect
from core.prd.harvest import harvest_milestone, milestone_signals, read_capability_map

DOC_NAME = "prd/prd-sow.md"


def _require_db(source_root: Path, dream_studio_home: Path | None) -> Path:
    from interfaces.cli.ds import resolve_installed_runtime_paths

    return resolve_installed_runtime_paths(
        source_root=source_root, dream_studio_home=dream_studio_home
    ).sqlite_path


def _mean(xs: list[float]) -> float:
    return round(sum(xs) / len(xs), 1) if xs else 0.0


def _auto_accomplished(closed_count: int, closed_titles: list[str]) -> str:
    if closed_count == 0:
        return "No closed work orders recorded."
    if not closed_titles:
        return f"Delivered {closed_count} work order(s)."
    head = "; ".join(closed_titles[:6])
    more = f" (+{len(closed_titles) - 6} more)" if len(closed_titles) > 6 else ""
    return f"Delivered {closed_count} work order(s): {head}{more}."


def rescore_prd(
    project_id: str,
    *,
    source_root: Path | None = None,
    dream_studio_home: Path | None = None,
    db_path: Path | None = None,
    planning_root: Path | None = None,
    files_db_path: Path | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Recompute the PRD+SOW score + render the living document to the docstore.

    Pure function of authority (studio.db) + docstore (files.db capability map) state at call
    time; see SPEC-0001. Pass ``source_root`` (production) or an explicit ``db_path`` /
    ``files_db_path`` (isolated tests); ``now`` fixes the refresh timestamp for determinism.
    """
    if db_path is None:
        if source_root is None:
            raise ValueError("rescore_prd requires source_root or an explicit db_path")
        db_path = _require_db(source_root, dream_studio_home)
    p_root = planning_root or (Path.cwd() / ".planning")

    cap_map = read_capability_map(db_path=files_db_path)
    capabilities = cap_map["capabilities"]
    linkage: dict[str, list[str]] = cap_map["milestone_capabilities"]
    overrides: dict[str, str] = cap_map["milestone_accomplished"]

    with _connect(db_path) as conn:
        ms_rows = conn.execute(
            "SELECT milestone_id, title, description, status FROM business_milestones"
            " WHERE project_id = ? ORDER BY order_index, created_at",
            (project_id,),
        ).fetchall()

        ms_entries: list[dict[str, Any]] = []
        score_by_completed: dict[str, float] = {}
        for mid, title, desc, status in ms_rows:
            ev = harvest_milestone(conn, mid, p_root, files_db_path=files_db_path)
            signals = milestone_signals(ev)
            score = _mean(signals)
            denom = max(1, ev["work_order_count"] + 3)  # WOs + 3 possible gate artifacts
            confidence = round(min(1.0, len(signals) / denom), 3)
            complete = status == "complete"
            if complete:
                accomplished = overrides.get(mid) or _auto_accomplished(
                    ev["closed_count"], ev["closed_titles"]
                )
            else:
                accomplished = "In progress -- not yet delivered."
            ms_entries.append(
                {
                    "milestone_id": mid,
                    "title": title,
                    "summary": title,
                    "set_out_to": (desc or title or "").strip(),
                    "accomplished": accomplished,
                    "score": score,
                    "confidence": confidence,
                    "status": status,
                    "capabilities": list(linkage.get(mid, [])),
                }
            )
            if complete:
                score_by_completed[mid] = score

    cap_entries: list[dict[str, Any]] = []
    total_w = 0.0
    weighted = 0.0
    delivered = 0
    for cap in capabilities:
        cid = cap["capability_id"]
        weight = float(cap.get("weight", 1.0))
        deliverers = [m for m, caps in linkage.items() if cid in caps and m in score_by_completed]
        if deliverers:
            sub = _mean([score_by_completed[m] for m in deliverers])
            cstatus = "scored"
            delivered += 1
        else:
            sub = 0.0
            cstatus = "not_delivered"
        cap_entries.append(
            {
                "capability_id": cid,
                "title": cap.get("title", cid),
                "weight": weight,
                "score": sub,
                "status": cstatus,
                "milestone_ids": deliverers,
            }
        )
        total_w += weight
        weighted += sub * weight

    overall = round(weighted / total_w, 1) if total_w else 0.0
    coverage = round(delivered / len(capabilities), 3) if capabilities else 0.0
    completed_confs = [e["confidence"] for e in ms_entries if e["status"] == "complete"]
    confidence = round(sum(completed_confs) / len(completed_confs), 3) if completed_confs else 0.0

    refreshed_at = now or datetime.now(UTC).isoformat()
    document = _render(
        project_id, overall, coverage, confidence, cap_entries, ms_entries, refreshed_at
    )

    from core.files.store import write_file

    write_file(
        DOC_NAME,
        document,
        "text/markdown",
        "planning",
        project_id=project_id,
        db_path=files_db_path,
    )

    return {
        "ok": True,
        "project_id": project_id,
        "overall_score": overall,
        "coverage": coverage,
        "confidence": confidence,
        "capabilities": cap_entries,
        "milestones": ms_entries,
        "document_ref": DOC_NAME,
        "refreshed_at": refreshed_at,
    }


def _render(
    project_id: str,
    overall: float,
    coverage: float,
    confidence: float,
    caps: list[dict[str, Any]],
    milestones: list[dict[str, Any]],
    refreshed_at: str,
) -> str:
    lines: list[str] = []
    lines.append("# Dream Studio - PRD + Statement of Work")
    lines.append("")
    lines.append(
        "> A derived, evidence-scored living document (ADR-0003 / SPEC-0001). Regenerated from "
        "authority + docstore state by `ds prd rescore`; do not hand-edit."
    )
    lines.append("")
    lines.append(f"- Project: {project_id}")
    lines.append(f"- Overall PRD score: {overall}/100")
    lines.append(f"- Coverage: {round(coverage * 100, 1)}% of capabilities delivered")
    lines.append(f"- Confidence: {confidence}")
    lines.append(f"- Refreshed: {refreshed_at}")
    lines.append("")
    lines.append("## Capabilities")
    lines.append("")
    lines.append("| Capability | Score | Status | Delivering milestones |")
    lines.append("| --- | --- | --- | --- |")
    for c in caps:
        n = len(c["milestone_ids"])
        deliv = f"{n} milestone(s)" if n else "-"
        lines.append(f"| {c['title']} | {c['score']}/100 | {c['status']} | {deliv} |")
    lines.append("")
    lines.append("## Statement of Work - Milestones")
    lines.append("")
    for m in milestones:
        caps_str = ", ".join(m["capabilities"]) if m["capabilities"] else "(none linked)"
        lines.append(f"### {m['title']}  -  {m['score']}/100  [{m['status']}]")
        lines.append(f"- Set out to: {m['set_out_to'] or '(no description)'}")
        lines.append(f"- Accomplished: {m['accomplished']}")
        lines.append(f"- Capabilities advanced: {caps_str}")
        lines.append(f"- Confidence: {m['confidence']}")
        lines.append("")
    return "\n".join(lines) + "\n"
