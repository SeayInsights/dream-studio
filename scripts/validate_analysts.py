#!/usr/bin/env python3
"""Validate that coach analyst YAMLs cover all known skills.

Reads skills/*/metadata.yml for the canonical skill list and compares
against the skills referenced in skills/coach/analysts/*.yml.

Exit 0: all skills covered.
Exit 1: one or more skills missing from analyst coverage.

Usage: py scripts/validate_analysts.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"
ANALYSTS_DIR = SKILLS_DIR / "coach" / "analysts"

# Skills excluded from analyst coverage requirements
EXCLUDED_SKILLS = {"coach"}  # coach doesn't analyse itself


def get_all_skills() -> set[str]:
    """Collect skill names from skills/*/metadata.yml name fields."""
    skills = set()
    for metadata_file in SKILLS_DIR.glob("*/metadata.yml"):
        try:
            text = metadata_file.read_text(encoding="utf-8")
        except OSError:
            continue
        match = re.search(r"^name:\s*['\"]?([^'\"\n]+)['\"]?", text, re.MULTILINE)
        if match:
            skills.add(match.group(1).strip())
        else:
            # Fall back to directory name
            skills.add(metadata_file.parent.name)
    return skills - EXCLUDED_SKILLS


def get_covered_skills() -> set[str]:
    """Collect skill names referenced in any coach analyst YAML."""
    covered = set()
    if not ANALYSTS_DIR.is_dir():
        return covered
    for analyst_file in ANALYSTS_DIR.glob("*.yml"):
        try:
            text = analyst_file.read_text(encoding="utf-8")
        except OSError:
            continue
        # Match skill names in lists, mappings, or inline values
        # Patterns: "- skill-name", "skill: skill-name", "skills: [a, b]"
        for match in re.finditer(r"['\"]?([a-z][a-z0-9-]+)['\"]?", text):
            token = match.group(1)
            if "-" in token or len(token) > 3:  # likely a skill name, not a keyword
                covered.add(token)
    return covered


def main() -> None:
    all_skills = get_all_skills()
    if not all_skills:
        print("ERROR: No skills found — check that skills/*/metadata.yml files exist.")
        sys.exit(1)

    covered = get_covered_skills()
    missing = all_skills - covered

    if not missing:
        print(f"PASS: all {len(all_skills)} skills covered in coach analyst YAMLs.")
        sys.exit(0)

    print(f"FAIL: {len(missing)} skill(s) missing from coach analyst coverage:")
    for skill in sorted(missing):
        print(f"  - {skill}")
    print(
        "\nAdd these skills to skills/coach/analysts/route-classifier.yml "
        "(or another analyst YAML) to fix this."
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
