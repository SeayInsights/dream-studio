"""Gap generation, dedup, and gap-work-order insertion for work-order verify.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/verify.py``. Holds the
grader-output-to-gap conversion helpers, the invented-threshold filter, the
stable gap-key/category dedup machinery, and the authority INSERT of spawned
gap work orders/tasks. No logic changes — extracted verbatim from the
original module.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

# ── Gap generation helpers ──────────────────────────────────────────────────────


def _violations_to_gaps(
    violations: list[dict[str, Any]],
    coverage_gaps: list[dict[str, Any]],
    migration_gaps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    if violations:
        tasks = [
            {
                "title": f"Fix {v.get('rule', 'violation')} in {v.get('file', 'unknown')}",
                "description": v.get("detail", ""),
            }
            for v in violations
        ]
        gaps.append(
            {
                "title": "Fix architectural violations flagged by correctness grader",
                "description": (
                    f"{len(violations)} architectural rule violation(s) detected in diff. "
                    "See review-verdict.json correctness.violations for details."
                ),
                "work_order_type": "cleanup",
                "tasks": tasks,
            }
        )
    if coverage_gaps:
        tasks = [
            {
                "title": (
                    f"Add tests for {g.get('function', g.get('fn', 'function'))} "
                    f"in {g.get('file', 'unknown')}"
                ),
                "description": "No test coverage found for this function/command.",
            }
            for g in coverage_gaps
        ]
        gaps.append(
            {
                "title": "Add missing test coverage",
                "description": (
                    f"{len(coverage_gaps)} public function(s) or command(s) lack test coverage."
                ),
                "work_order_type": "infrastructure",
                "tasks": tasks,
            }
        )
    if migration_gaps:
        tasks = [
            {"title": g.get("item", "Fix migration gap"), "description": ""} for g in migration_gaps
        ]
        gaps.append(
            {
                "title": "Fix migration hygiene issues",
                "description": (
                    f"{len(migration_gaps)} migration hygiene issue(s) found. "
                    "See review-verdict.json correctness.migration_gaps."
                ),
                "work_order_type": "infrastructure",
                "tasks": tasks,
            }
        )
    return gaps


def _quality_issues_to_gaps(error_issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not error_issues:
        return []
    tasks = [
        {
            "title": (f"Fix {i.get('category', 'quality')} issue in {i.get('file', 'unknown')}"),
            "description": i.get("detail", ""),
        }
        for i in error_issues
    ]
    return [
        {
            "title": "Fix error-severity quality issues",
            "description": (
                f"{len(error_issues)} error-severity quality issue(s) detected. "
                "See review-verdict.json quality.issues."
            ),
            "work_order_type": "cleanup",
            "tasks": tasks,
        }
    ]


def _migration_risks_to_gaps(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    error_risks = [r for r in risks if r.get("severity") == "error"]
    if not error_risks:
        return []
    tasks = [
        {
            "title": f"Resolve {r.get('category', 'migration')} risk",
            "description": r.get("detail", ""),
        }
        for r in error_risks
    ]
    return [
        {
            "title": "Resolve migration safety risks",
            "description": (
                f"{len(error_risks)} error-severity migration risk(s) found. "
                "See review-verdict.json migration.risks."
            ),
            "work_order_type": "infrastructure",
            "tasks": tasks,
        }
    ]


# ── Gap WO insertion ────────────────────────────────────────────────────────────


# WO-SPAWN-LOOP-FIX: regex for numeric thresholds (line counts, coverage %, etc.)
# that a grader might fabricate. Used to reject gaps that invent a threshold absent
# from the explicit acceptance-criteria text.
_THRESHOLD_RE = re.compile(
    r"(?:<=|>=|<|>|≤|≥|under|below|at most|no more than|at least|over)?\s*\d+\s*"
    r"(?:lines?|%|percent|chars?|characters?|tokens?|loc)\b",
    re.IGNORECASE,
)


def _gap_category(gap: dict[str, Any]) -> str:
    """Return a stable category for a gap, independent of free-text phrasing.

    Prefers an explicit ``category`` field emitted by the grader. Falls back to a
    normalized form of the title (lowercased, alphanumerics only) so legacy gaps
    without a category still dedup against an identical title. Rephrased titles
    only dedup when the grader supplies a stable ``category`` (WO-SPAWN-LOOP-FIX T1).
    """
    explicit = (gap.get("category") or "").strip().lower()
    if explicit:
        return re.sub(r"[^a-z0-9]+", "-", explicit).strip("-")
    title = (gap.get("title") or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", title).strip("-")


# WO-GAP-DEDUPE-CLASS: generic advisory gap categories that are the SAME finding
# on any work order (they do not describe a specific WO's content). These dedup
# project-wide by category alone, so the class spawns at most one open tracking WO
# instead of a near-duplicate per reviewed WO. Content-specific categories
# (missing-tests, task-N-incomplete, …) stay scoped to the reviewed WO.
_ADVISORY_PROJECT_WIDE_CATEGORIES = frozenset({"missing-behavioral-ac"})


def _gap_key(reviewed_work_order_id: str, gap: dict[str, Any]) -> str:
    """Stable dedup key for a spawned gap.

    Normally (reviewed WO id + gap category), stored as a ``[gap-key: ...]`` marker
    on the spawned WO's description so later re-reviews recognize prior spawns
    regardless of title phrasing (T1). For generic advisory categories
    (``_ADVISORY_PROJECT_WIDE_CATEGORIES``) the reviewed-WO id is dropped so the
    class dedups project-wide — otherwise the same advisory finding respawns a
    near-duplicate WO on every reviewed WO (WO-GAP-DEDUPE-CLASS).
    """
    category = _gap_category(gap)
    if category in _ADVISORY_PROJECT_WIDE_CATEGORIES:
        return f"advisory::{category}"
    return f"{reviewed_work_order_id}::{category}"


def _gap_key_marker(gap_key: str) -> str:
    return f"[gap-key: {gap_key}]"


def _filter_invented_threshold_gaps(
    gaps: list[dict[str, Any]], acceptance_text: str
) -> list[dict[str, Any]]:
    """Drop gaps that fabricate a numeric threshold absent from the AC text.

    A grader must only flag gaps against EXPLICIT acceptance criteria. If a gap's
    title/description/tasks introduce a numeric threshold (e.g. "<=50 lines",
    "90% coverage") that does not appear in *acceptance_text*, the gap is an
    invented threshold and is rejected (WO-SPAWN-LOOP-FIX T2).
    """
    ac_thresholds = {
        m.group(0).lower().replace(" ", "") for m in _THRESHOLD_RE.finditer(acceptance_text)
    }
    kept: list[dict[str, Any]] = []
    for gap in gaps:
        text_parts = [gap.get("title", ""), gap.get("description", "")]
        for task in gap.get("tasks", []):
            text_parts.append(task.get("title", ""))
            text_parts.append(task.get("description", ""))
        gap_text = " ".join(text_parts)
        gap_thresholds = {
            m.group(0).lower().replace(" ", "") for m in _THRESHOLD_RE.finditer(gap_text)
        }
        invented = gap_thresholds - ac_thresholds
        if invented:
            continue  # fabricated threshold not grounded in the AC — reject
        kept.append(gap)
    return kept


def _insert_gap_work_orders(
    conn: Any,
    *,
    gaps: list[dict[str, Any]],
    project_id: str,
    milestone_id: str | None,
    reviewed_work_order_id: str,
    reviewed_wo_title: str,
    reviewed_wo_sequence: int | None,
) -> list[dict[str, Any]]:
    now = datetime.now(UTC).isoformat()
    spawned: list[dict[str, Any]] = []

    base_seq = reviewed_wo_sequence or 0
    if milestone_id:
        max_seq_row = conn.execute(
            "SELECT MAX(sequence_order) FROM business_work_orders WHERE milestone_id = ?",
            (milestone_id,),
        ).fetchone()
        if max_seq_row and max_seq_row[0] is not None:
            base_seq = max(base_seq, max_seq_row[0])

    new_wo_counter = 0
    for gap in gaps:
        wo_type = gap.get("work_order_type", "cleanup")
        gap_title = gap["title"]
        gap_key = _gap_key(reviewed_work_order_id, gap)
        marker = _gap_key_marker(gap_key)

        # Dedup on the stable gap key, NOT the free-text title, scoped by project_id
        # so null-milestone gaps still dedup (T3). Match across ANY status so a closed
        # prior spawn is never re-spawned (T4 respawn cap). Prefer an open WO so we can
        # merge tasks into it; a closed match means skip-and-log.
        existing_row = conn.execute(
            "SELECT work_order_id, status FROM business_work_orders"
            " WHERE project_id = ? AND instr(description, ?) > 0"
            " ORDER BY CASE status"
            "   WHEN 'in_progress' THEN 0 WHEN 'created' THEN 1 ELSE 2 END"
            " LIMIT 1",
            (project_id, marker),
        ).fetchone()

        if existing_row and existing_row[1] not in ("created", "in_progress"):
            # T4 respawn cap: a prior spawn for this gap key already exists (closed).
            # Never spawn it again — skip and record the suppression.
            spawned.append(
                {
                    "work_order_id": existing_row[0],
                    "title": gap_title,
                    "type": wo_type,
                    "gap_key": gap_key,
                    "respawn_suppressed": True,
                }
            )
            continue

        if existing_row:
            target_wo_id = existing_row[0]
            for task in gap.get("tasks", []):
                task_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO business_tasks"
                    " (task_id, work_order_id, project_id, title, description,"
                    "  status, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
                    (
                        task_id,
                        target_wo_id,
                        project_id,
                        task.get("title", ""),
                        task.get("description", ""),
                        now,
                        now,
                    ),
                )
            spawned.append(
                {
                    "work_order_id": target_wo_id,
                    "title": gap_title,
                    "type": wo_type,
                    "gap_key": gap_key,
                    "merged_into_existing": True,
                }
            )
        else:
            new_wo_id = str(uuid.uuid4())
            seq = base_seq + new_wo_counter + 1
            new_wo_counter += 1
            desc = (
                f"Spawned by review of '{reviewed_wo_title}' on {now[:10]}: "
                f"{gap.get('description', '')} {marker}"
            )
            conn.execute(
                "INSERT INTO business_work_orders"
                " (work_order_id, project_id, milestone_id, title, description,"
                "  work_order_type, status, sequence_order, created_at, updated_at, last_updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, 'created', ?, ?, ?, ?)",
                (
                    new_wo_id,
                    project_id,
                    milestone_id,
                    gap_title,
                    desc,
                    wo_type,
                    seq,
                    now,
                    now,
                    now,
                ),
            )
            for task in gap.get("tasks", []):
                task_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO business_tasks"
                    " (task_id, work_order_id, project_id, title, description,"
                    "  status, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
                    (
                        task_id,
                        new_wo_id,
                        project_id,
                        task.get("title", ""),
                        task.get("description", ""),
                        now,
                        now,
                    ),
                )
            spawned.append(
                {
                    "work_order_id": new_wo_id,
                    "title": gap_title,
                    "type": wo_type,
                    "gap_key": gap_key,
                }
            )

    return spawned
