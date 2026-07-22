"""PRD (project requirements doc) authority helpers.

WO-GF-API-ROUTES: split out of project_helpers.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .project_helpers_utils import _as_int

# ── PRD helpers ──────────────────────────────────────────────────────────────


def _resolve_prd_file(project: dict[str, Any], file_path: str | None) -> Path | None:
    if not file_path:
        return None
    candidate = Path(file_path)
    if candidate.is_absolute():
        return candidate
    project_path = project.get("project_path")
    if not project_path:
        return None
    root = Path(str(project_path))
    if not root.is_absolute():
        root = Path.home() / "builds" / root
    return root / candidate


def _safe_prd_summary(project: dict[str, Any]) -> dict[str, Any]:
    prd_file = _resolve_prd_file(project, project.get("latest_prd_file_path"))
    if not prd_file or not prd_file.exists() or not prd_file.is_file():
        return {
            "available": False,
            "summary": "PRD content was not available from the recorded source ref.",
            "source_ref": project.get("latest_prd_file_path"),
            "safe_read": False,
        }
    lowered_parts = {part.lower() for part in prd_file.parts}
    if lowered_parts.intersection({".git", ".claude", ".codex", "secrets", "credentials"}):
        return {
            "available": False,
            "summary": "PRD path is in a sensitive or adapter-runtime area and was not read.",
            "source_ref": str(prd_file),
            "safe_read": False,
        }
    try:
        text = prd_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {
            "available": False,
            "summary": "PRD source ref could not be read.",
            "source_ref": str(prd_file),
            "safe_read": False,
        }
    lines = [
        line.strip("# ").strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("<!--")
    ]
    summary_lines = lines[:6]
    return {
        "available": True,
        "summary": " / ".join(summary_lines)[:800] if summary_lines else "PRD file exists.",
        "source_ref": str(prd_file),
        "safe_read": True,
        "line_count": len(text.splitlines()),
    }


def _build_prd_authority_status(project: dict[str, Any]) -> dict[str, Any]:
    prd_count = _as_int(project.get("prd_count"))
    latest_status = str(project.get("latest_prd_status") or "").lower()
    summary = _safe_prd_summary(project) if prd_count else None
    if not prd_count:
        status = "draft_generated"
        confidence = "low"
        reason = "No current PRD authority row is linked; the dashboard exposes an explicit draft-required state instead of inventing claims."
        manual_review_flags = ["prd_missing_current_authority"]
    elif latest_status in {"superseded", "stale", "archived"}:
        status = "stale_superseded"
        confidence = "medium"
        reason = "Latest linked PRD status indicates stale or superseded authority."
        manual_review_flags = ["prd_supersession_review"]
    elif summary and summary["available"]:
        status = "current"
        confidence = "medium"
        reason = "A linked PRD authority row and readable source ref are available."
        manual_review_flags = []
    else:
        status = "needs_update"
        confidence = "low"
        reason = "A PRD row exists but the recorded source ref is missing or unreadable."
        manual_review_flags = ["prd_source_ref_review"]
    return {
        "status": status,
        "latest_lifecycle_status": project.get("latest_prd_status"),
        "title": project.get("latest_prd_title"),
        "file_path": project.get("latest_prd_file_path"),
        "created_at": project.get("latest_prd_created_at"),
        "count": prd_count,
        "confidence": confidence,
        "reason": reason,
        "summary": (
            summary["summary"]
            if summary
            else "Draft PRD required; evidence is insufficient for product claims."
        ),
        "source_refs": (
            [project.get("latest_prd_file_path")] if project.get("latest_prd_file_path") else []
        ),
        "evidence_refs": [summary["source_ref"]] if summary and summary.get("source_ref") else [],
        "manual_review_flags": manual_review_flags,
        "derived_view": True,
        "primary_authority": False,
    }
