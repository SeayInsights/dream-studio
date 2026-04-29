"""Escalation candidates — skills accumulating draft lessons without updates.

Reads the draft-lessons directory and counts how many lessons reference each
skill. Returns skills that have reached the escalation threshold, signalling
that the skill's SKILL.md or gotchas.yml should be reviewed and updated.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import paths


def get_escalation_candidates(threshold: int = 3) -> list[dict]:
    """Return skills with >= threshold unreviewed draft lessons.

    Each entry: {"skill": str, "lesson_count": int, "lesson_files": list[str]}
    """
    lessons_dir = paths.meta_dir() / "draft-lessons"
    if not lessons_dir.is_dir():
        return []

    skill_counts: dict[str, list[str]] = {}

    for lesson_file in lessons_dir.glob("*.md"):
        try:
            text = lesson_file.read_text(encoding="utf-8")
        except OSError:
            continue

        # Skip already-promoted lessons
        if "Status: PROMOTED" in text:
            continue

        # Extract skill references from "Applies to" or "Source" sections
        # Also check filename for skill name patterns
        referenced_skills = _extract_skill_refs(text, lesson_file.name)
        for skill in referenced_skills:
            skill_counts.setdefault(skill, []).append(lesson_file.name)

    return [
        {"skill": skill, "lesson_count": len(files), "lesson_files": files}
        for skill, files in skill_counts.items()
        if len(files) >= threshold
    ]


def _extract_skill_refs(text: str, filename: str) -> list[str]:
    """Extract skill names from lesson text and filename."""
    skills = set()

    # Match "Applies to: debug, build" style lines
    applies_match = re.search(r"##\s*Applies to\s*\n([^\n#]+)", text, re.IGNORECASE)
    if applies_match:
        raw = applies_match.group(1)
        for token in re.split(r"[,\s/]+", raw.strip()):
            token = token.strip().lower()
            if token:
                skills.add(token)

    # Match "Source: debug session" style lines
    source_match = re.search(r"Source:\s*([^\n]+)", text, re.IGNORECASE)
    if source_match:
        raw = source_match.group(1).lower()
        for known in _known_skills():
            if known in raw:
                skills.add(known)

    # Infer from filename: "2026-04-29-debug-d1-binding.md" → "debug"
    name_parts = filename.lower().replace(".md", "").split("-")
    for part in name_parts:
        if part in _known_skills():
            skills.add(part)

    return list(skills)


def _known_skills() -> set[str]:
    """Return the set of known skill names from the skills directory."""
    skills_dir = Path(__file__).resolve().parents[2] / "skills"
    if not skills_dir.is_dir():
        return set()
    return {p.name for p in skills_dir.iterdir() if p.is_dir() and not p.name.startswith(".")}
