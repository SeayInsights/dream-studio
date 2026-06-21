"""Tests for the leanness gate + the build-skill pre-creation checklist (WO-LEANNESS-GATE)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_gate_runs():
    """The leanness gate module imports and exposes a callable main()."""
    from core.gates import leanness

    assert callable(leanness.main)
    assert leanness.SRC, "gate must scan at least one source dir"


def test_gate_wired_in_prepush():
    """The gate is declared (advisory) in the pre-push workflow."""
    txt = (ROOT / "canonical" / "workflows" / "pre-push.yaml").read_text(encoding="utf-8")
    assert "core.gates.leanness" in txt
    assert "tier: advisory" in txt


def test_build_skill_has_checklist():
    """The canonical build skill embeds the 5 pre-creation leanness checks."""
    txt = (ROOT / "canonical" / "skills" / "core" / "modes" / "build" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "Leanness Checks" in txt
    for phrase in ("Refactor over new", "Simplest form", "No duplication", "Not dead"):
        assert phrase in txt, f"missing check: {phrase}"
