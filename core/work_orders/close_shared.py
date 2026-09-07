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


#: Grader roles, in the order they are declared. Used as the stable tie-break when a
#: verdict carries no scores.
_VERDICT_ROLES = ("completion", "correctness", "quality", "falsification")


def verdict_score_line(verdict: dict[str, Any]) -> str:
    """`quality 0.62, correctness 0.79, completion 1.00 (composite 0.86)`, or "".

    Named in the failure message so a reader can see WHICH role objected without opening
    the stored artifact. Without it the message carries one paragraph and no indication of
    where it came from.
    """
    scores = verdict.get("scores")
    if not isinstance(scores, dict):
        return ""
    parts = [
        (role, float(scores[f"{role}_score"]))
        for role in _VERDICT_ROLES
        if isinstance(scores.get(f"{role}_score"), (int, float))
    ]
    if not parts:
        return ""
    ranked = ", ".join(f"{role} {value:.2f}" for role, value in sorted(parts, key=lambda p: p[1]))
    composite = scores.get("composite_score")
    if isinstance(composite, (int, float)):
        return f"{ranked} (composite {float(composite):.2f})"
    return ranked


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
        # LEAD WITH THE ROLE THAT SCORED WORST, not with whichever role comes first
        # alphabetically-by-declaration. Measured on WO 17f20d48: completion scored 1.0
        # and wrote a glowing paragraph ("both resolve and pass"), while correctness
        # (0.786) and quality (0.62) carried the violations that failed the composite
        # (0.8598). The gate therefore printed "review failed - [everything is great]",
        # which reads as a broken gate rather than as a real finding, and cost a reader
        # twenty minutes concluding exactly that. The verdict was right; the sentence it
        # chose was from the one role that had nothing to report.
        #
        # `sorted` is stable, so roles with no score keep the original declaration order
        # and a verdict carrying no scores at all behaves exactly as before.
        scores = verdict.get("scores") if isinstance(verdict.get("scores"), dict) else {}

        def _rank(role: str) -> float:
            value = scores.get(f"{role}_score")
            # An unscored role ranks last: absence of a score is not evidence of a problem.
            return float(value) if isinstance(value, (int, float)) else 1.0

        for section in sorted(_VERDICT_ROLES, key=_rank):
            part = verdict.get(section)
            if isinstance(part, dict) and (part.get("summary") or "").strip():
                summary = str(part["summary"]).strip()
                break
    findings: list[Any] = []
    for key in ("failure_reasons", "gaps", "spawned_work_orders"):
        value = verdict.get(key)
        if isinstance(value, list):
            findings.extend(value)
    # ROLE VIOLATIONS ARE FINDINGS TOO. correctness and quality record `violations` and
    # write no `summary` at all, so a verdict whose ONLY objections live there produced a
    # findings list that was empty while the work order was failing on exactly those
    # objections -- and the summary came from the one role with nothing to report.
    for role in _VERDICT_ROLES:
        part = verdict.get(role)
        if isinstance(part, dict):
            violations = part.get("violations")
            if isinstance(violations, list):
                findings.extend(violations)
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
