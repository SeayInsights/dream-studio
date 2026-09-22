"""WO 504c0ff8: domain skills must not direct writes/reads to the denied .planning disk tree.

The files-in-DB direction (P3) moved working state into the docstore and the on-edit hook
DENIES .planning disk writes. The domain skills (fullstack api-contract, website
direction-lock / brand) previously instructed writing/reading loose .planning/* files —
now flipped to the `ds files` docstore. This guards against regression.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOMAINS = REPO / "canonical" / "skills" / "domains" / "modes"

# Concrete .planning artifact paths the domain skills must no longer reference (write or
# read). Bare ".planning" is allowed — the flipped text explains that ".planning/ disk
# writes are denied" — so we assert only the specific artifact-path prefixes are gone.
FORBIDDEN_PATHS = (".planning/api-contract", ".planning/direction-lock", ".planning/brand")

# `fullstack` and `website` were routable packs living inside the domains tree; they now
# sit at canonical/skills/<pack>/ like every other pack. The rule these files carry is
# unchanged — only where they live.
# DOMAINS already ends in /modes, so the skills root is two levels up.
SKILLS = DOMAINS.parent.parent
FULLSTACK = SKILLS / "fullstack"
WEBSITE = SKILLS / "website"

DOMAIN_SKILL_FILES = [
    FULLSTACK / "SKILL.md",
    FULLSTACK / "templates" / "api-contract.md",
    FULLSTACK / "modes" / "frontend" / "SKILL.md",
    FULLSTACK / "modes" / "backend" / "SKILL.md",
    FULLSTACK / "modes" / "integrate" / "SKILL.md",
    WEBSITE / "modes" / "direction" / "SKILL.md",
    WEBSITE / "modes" / "brand" / "SKILL.md",
]


def test_domain_skills_have_no_planning_artifact_paths():
    offenders = []
    for f in DOMAIN_SKILL_FILES:
        assert f.is_file(), f"expected domain skill file missing: {f}"
        text = f.read_text(encoding="utf-8")
        for bad in FORBIDDEN_PATHS:
            if bad in text:
                offenders.append(f"{f.relative_to(REPO).as_posix()} still references {bad!r}")
    assert not offenders, "domain skills still write/read .planning disk artifacts:\n" + "\n".join(
        offenders
    )


def test_flipped_directives_use_the_docstore():
    fullstack = (FULLSTACK / "SKILL.md").read_text(encoding="utf-8")
    assert 'ds files write "api-contract.json" --category planning' in fullstack
    assert 'ds files read "api-contract.json"' in fullstack

    direction = (WEBSITE / "modes" / "direction" / "SKILL.md").read_text(encoding="utf-8")
    assert 'ds files write "direction-lock.json" --category planning' in direction
