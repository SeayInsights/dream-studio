"""The build skill embeds the five pre-creation leanness checks.

WHAT WAS HERE AND IS NOT. This file also tested `core.gates.leanness` — that it imported,
and that pre-push wired it. Commit `db4c23f` removed that gate as one of thirteen that
"audit the repo's own bookkeeping ... none tested whether Dream Studio works", taking
pre-push from 39 gates to 15. The module went; these two tests stayed, so they failed on
every full-ci run afterwards with `ImportError: cannot import name 'leanness'` and an
assertion that the manifest still named it.

A test of removed behaviour is deleted, not kept alive — otherwise the suite reports a
regression where there was a decision, and the next reader cannot tell which. The file is
renamed because `test_leanness_gate.py` named a gate that no longer exists.

The checklist itself survives on its own merit: it is the operator's five pre-creation
checks, and the build skill is where an author meets them.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_build_skill_has_checklist():
    """The canonical build skill embeds the 5 pre-creation leanness checks."""
    txt = (ROOT / "canonical" / "skills" / "core" / "modes" / "build" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "Leanness Checks" in txt
    for phrase in ("Refactor over new", "Simplest form", "No duplication", "Not dead"):
        assert phrase in txt, f"missing check: {phrase}"
