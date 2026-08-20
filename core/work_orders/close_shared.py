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
    is activated) gate-satisfiable during the transition. Provenance envelopes
    (WO-VERIFY-PROVENANCE) are unwrapped transparently.
    """
    content, _ = _artifact_with_envelope(work_order_id, wo_dir, kind, db_path)
    return content


def verdict_evidence(verdict: dict[str, Any]) -> tuple[str, list[Any]]:
    """``(summary, findings)`` from a verify verdict, read where verify WRITES them.

    THE SHAPE WAS INVENTED, THEN MEASURED. WO-VERDICT-PARTIAL-WRITE task 3 checked
    top-level ``summary`` / ``failure_reasons`` and treated their absence as an
    incomplete record. Real verdicts carry NEITHER key: the prose lives under
    ``completion.summary`` and the findings under ``gaps`` /
    ``spawned_work_orders``. So a verdict with three real gaps and a 0.793 composite
    was reported as "UNREVIEWABLE - incomplete record", telling an operator to
    re-run verify instead of showing them the gaps.

    That is the inversion the same commit called "worse than the defect": a real
    failure softened into inconclusive. It shipped because the shape was assumed
    rather than read from a stored verdict.

    Top-level keys are still accepted first, since attestations and hand-built
    verdicts in tests do use them.
    """
    summary = (verdict.get("summary") or "").strip()
    if not summary:
        for section in ("completion", "correctness", "quality"):
            part = verdict.get(section)
            if isinstance(part, dict) and (part.get("summary") or "").strip():
                summary = str(part["summary"]).strip()
                break
    findings: list[Any] = []
    for key in ("failure_reasons", "gaps", "spawned_work_orders"):
        value = verdict.get(key)
        if isinstance(value, list):
            findings.extend(value)
    return summary, findings


def _artifact_with_envelope(
    work_order_id: str, wo_dir: Path, kind: str, db_path: Path | None
) -> tuple[str | None, dict[str, Any] | None]:
    """Like ``_artifact_text`` but also returns the provenance envelope.

    ``envelope`` is None for legacy bare-text artifacts (both stores) and for
    absent artifacts — gates that require provenance treat that as a failure
    with a regeneration message (WO-VERIFY-PROVENANCE).
    """
    from core.work_orders.artifact_envelope import unwrap
    from core.work_orders.artifacts import KIND_TO_FILENAME, get_wo_artifact_envelope

    content, envelope = get_wo_artifact_envelope(work_order_id, kind, db_path=db_path)
    if content is not None:
        return content, envelope
    fpath = wo_dir / KIND_TO_FILENAME[kind]
    if fpath.is_file():
        return unwrap(fpath.read_text(encoding="utf-8"))
    return None, None


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
