"""Escalation candidates — skills accumulating draft lessons without updates.

Reads the draft-lessons directory and counts how many lessons reference each
skill. Returns skills that have reached the escalation threshold, signalling
that the skill's SKILL.md or gotchas.yml should be reviewed and updated.

Promotion logic (future implementation):
- Load promotion-rules.yml from skills/quality/modes/learn/
- Score each draft lesson based on evidence count, confidence, recency
- Auto-reject lessons matching auto_reject criteria
- Promote lessons reaching auto_promote_threshold if require_director_review=false
- If require_director_review=true, surface candidates but wait for approval
- Move promoted lessons to promote_to targets (gotchas.yml, memory/)
- Archive promoted drafts to meta/lessons/ with Status: PROMOTED
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from core.config import paths

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
        # Infer skill from source field or lesson_id
        source = row.get("source", "")
        lesson_id = row.get("lesson_id", "")
        referenced_skills = _extract_skill_refs_from_db(source, lesson_id, known)
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
    """Return the set of known skill names from the skills directory."""
    skills_dir = Path(__file__).resolve().parents[2] / "skills"
    if not skills_dir.is_dir():
        return set()
    return {p.name for p in skills_dir.iterdir() if p.is_dir() and not p.name.startswith(".")}


# ============================================================================
# Promotion logic — to be implemented
# ============================================================================
# Future implementation will add:
# - load_promotion_rules() → reads skills/quality/modes/learn/promotion-rules.yml
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
