"""Every mode packs.yaml declares has a SKILL.md, and nothing ships a mode without one.

WHY THIS FILE EXISTS. `ds-project/resume` was declared in packs.yaml and carried a
metadata.yml with eleven triggers -- `continue:`, `what's next:`, `what should I do:` --
and had no SKILL.md. Its content had been inlined into the 30 KB pack file. The projector
shipped the directory into every install as it stood: triggers, no skill. The routing
collector dropped it (it requires a SKILL.md), so the operator's most natural phrases
were declared, installed, and routed to nothing. `git log --diff-filter=D` shows the
file was never deleted; it was never written. Nothing checked, for as long as the
declaration existed.

Two directions, because the failure has two shapes: a declaration with no file, and a
file set (metadata.yml) that ships without the skill it describes.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS = REPO_ROOT / "canonical" / "skills"


def _pack_dir(name: str, spec: dict) -> Path:
    """packs.yaml may point a pack at a directory with a different name (`meta` lives in
    canonical/skills/workflow). Resolve the way the projector does."""
    skill_path = spec.get("skill_path")
    if skill_path:
        return REPO_ROOT / skill_path
    return SKILLS / name


def _declared_modes() -> list[tuple[str, str, Path]]:
    packs = yaml.safe_load((REPO_ROOT / "packs.yaml").read_text(encoding="utf-8"))["packs"]
    out = []
    for name, spec in packs.items():
        for mode in (spec or {}).get("modes") or []:
            out.append((name, mode, _pack_dir(name, spec or {}) / "modes" / mode / "SKILL.md"))
    return out


def test_every_declared_mode_has_a_skill_file():
    missing = [f"{p}/{m}" for p, m, path in _declared_modes() if not path.is_file()]
    assert missing == [], (
        "packs.yaml declares modes with no SKILL.md -- a trigger that routes to nothing, "
        f"shipped to every install: {missing}"
    )


def test_no_mode_directory_ships_metadata_without_a_skill():
    """The other shape: the directory exists, has triggers, and no skill. The projector
    copies directories, so this is exactly what an install receives."""
    orphans = [
        str(meta.parent.relative_to(SKILLS)).replace("\\", "/")
        for meta in SKILLS.glob("*/modes/*/metadata.yml")
        if not (meta.parent / "SKILL.md").is_file()
    ]
    assert orphans == [], f"metadata.yml with no SKILL.md beside it: {orphans}"


def test_the_check_sees_the_real_tree():
    """A guard that walked an empty list would pass on a stub. Eighty-odd modes are
    declared; the number is a floor, not a pin, so a dissolution that removes a pack does
    not have to edit this file."""
    declared = _declared_modes()
    assert len(declared) > 60, f"only {len(declared)} declared modes -- has packs.yaml moved?"
    assert any(p == "core" and m == "build" for p, m, _ in declared)
