"""Escalation candidates — skills accumulating draft lessons without updates.

Reads the draft-lessons directory and counts how many lessons reference each
skill. Returns skills that have reached the escalation threshold, signalling
that the skill's SKILL.md or gotchas.yml should be reviewed and updated.

Promotion logic (future implementation):
- Load promotion-rules.yml from skills/core/modes/learn/
- Score each draft lesson based on evidence count, confidence, recency
- Auto-reject lessons matching auto_reject criteria
- Promote lessons reaching auto_promote_threshold if require_director_review=false
- If require_director_review=true, surface candidates but wait for approval
- Move promoted lessons to promote_to targets (gotchas.yml, memory/)
- Archive promoted drafts to meta/lessons/ with Status: PROMOTED
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path for canonical imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def get_escalation_candidates(threshold: int = 3) -> list[dict]:
    """Return skills with >= threshold unreviewed draft lessons (from DB raw_lessons).

    Each entry: {"skill": str, "lesson_count": int, "lesson_ids": list[str]}
    """
    try:
        from core.event_store.studio_db import get_pending_lessons
        from core.config import paths as _paths

        rows = get_pending_lessons(db_path=_paths.state_dir() / "studio.db")
    except Exception:
        return []

    known = _known_skills()
    skill_counts: dict[str, list[str]] = {}

    for row in rows:
        lesson_id = row.get("lesson_id", "")
        # raw_lessons carries a skill_id column; prefer it over guessing from prose.
        declared = (row.get("skill_id") or "").strip()
        if declared:
            skill_counts.setdefault(declared, []).append(lesson_id)
            continue
        referenced_skills = _extract_skill_refs_from_db(row.get("source", ""), lesson_id, known)
        for skill in referenced_skills:
            skill_counts.setdefault(skill, []).append(lesson_id)

    return [
        {"skill": skill, "lesson_count": len(ids), "lesson_ids": ids}
        for skill, ids in skill_counts.items()
        if len(ids) >= threshold
    ]


def _extract_skill_refs_from_db(source: str, lesson_id: str, known: set[str]) -> list[str]:
    """Extract skill names from a DB row's source field and lesson_id."""
    skills = set()
    src = source.lower()
    for k in known:
        if k in src:
            skills.add(k)
    # Infer from lesson_id slug: "correction-pattern-debug-..." → "debug"
    for part in lesson_id.lower().split("-"):
        if part in known:
            skills.add(part)
    return list(skills)


def _known_skills() -> set[str]:
    """Pack and mode names, read from the tracked canonical source.

    This read used to point at ``<repo>/skills``, which .gitignore excludes as a generated
    projection. On this machine that directory held one entry, ``__pycache__``, so the known
    set was ``{"__pycache__"}``, no lesson could ever match a skill name, and
    ``get_escalation_candidates`` returned an empty list on every call -- including from
    ``on-meta-review`` and ``control/review/engine``. A committed module depending on a path
    git does not ship is the gitignore-phantom shape; that gate is diff-scoped and this file
    had not been touched since it was written.

    Mode names are included alongside pack names because a lesson's ``source`` records the
    mode that produced it (``build``, ``review``, ``debug``), not the pack.
    """
    canonical = Path(__file__).resolve().parents[2] / "canonical" / "skills"
    if not canonical.is_dir():
        return set()
    names: set[str] = set()
    for pack in canonical.iterdir():
        if not pack.is_dir() or pack.name.startswith((".", "_")):
            continue
        names.add(pack.name)
        modes = pack / "modes"
        if modes.is_dir():
            names.update(
                m.name for m in modes.iterdir() if m.is_dir() and not m.name.startswith((".", "_"))
            )
    return names


# ============================================================================
# Promotion logic — to be implemented
# ============================================================================
# Future implementation will add:
# - load_promotion_rules() → reads skills/core/modes/learn/promotion-rules.yml
# - score_lesson(lesson_file: Path) → float score based on evidence/confidence/recency
# - should_auto_reject(lesson_data: dict, rules: dict) → bool
# - promote_lesson(lesson_file: Path, target: str) → moves to gotchas.yml or memory/
# - archive_promoted(lesson_file: Path) → moves to meta/lessons/ with Status: PROMOTED
#
# Example flow:
# 1. Scan meta/draft-lessons/ for lessons with Status: DRAFT
# 2. Score each lesson using promotion-rules.yml weights
# 3. Auto-reject lessons matching auto_reject criteria
# 4. If score >= auto_promote_threshold:
#    - If require_director_review=true: surface for approval
#    - If require_director_review=false: auto-promote to target
# 5. Archive promoted lessons with timestamp and promotion target
# ============================================================================
