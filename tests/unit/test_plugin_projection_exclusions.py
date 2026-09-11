"""Every canonical skill either ships or declares why it does not.

THE FINDING THIS COMES FROM. A verify run reported `ds-bootstrap/SKILL.md` as a stale
projection -- "still not projected and carries no recorded exclusion (missing is not
fresh)". The exclusion WAS deliberate and WAS explained, in prose, in the module docstring
of integrations/marketplace/plugin_dist.py. A reviewer reading the parity report could not
see that, and neither could any check: "excluded on purpose" and "somebody forgot to
regenerate" produced the identical observation of a missing file.

That is the same shape as a lane with no detector and a value with no reader -- a fact
that exists somewhere no consumer looks. The remedy is not more prose. It is that the
absence is DECLARED where the check reads, with a reason, so silence stops being
ambiguous.
"""

from __future__ import annotations

from pathlib import Path

from integrations.marketplace.plugin_dist import NOT_PROJECTED, projection_exclusion

REPO_ROOT = Path(__file__).resolve().parents[2]
_CANONICAL_SKILLS = REPO_ROOT / "canonical" / "skills"
_SHIPPED_SKILLS = REPO_ROOT / "dist" / "plugin" / "skills"


def _canonical_skill_dirs() -> list[str]:
    return sorted(
        d.name for d in _CANONICAL_SKILLS.iterdir() if d.is_dir() and (d / "SKILL.md").is_file()
    )


def test_every_declared_exclusion_carries_a_reason():
    """An entry with no reason is the same silence one directory further in."""
    assert NOT_PROJECTED, "the exclusion table is empty; nothing declares anything"
    for name, reason in NOT_PROJECTED.items():
        assert isinstance(reason, str) and len(reason.strip()) >= 20, (
            f"{name} is excluded with no usable reason ({reason!r}). The point of the "
            "table is that the absence stops being ambiguous."
        )


def test_ds_bootstrap_is_declared_rather_than_merely_absent():
    """The specific case a review could not tell apart from staleness."""
    reason = projection_exclusion("ds-bootstrap")
    assert reason, (
        "ds-bootstrap ships nowhere and declares no reason, so a parity report cannot "
        "distinguish it from a projection somebody forgot to regenerate"
    )
    assert "not a user-invocable skill" in reason


def test_a_skill_that_ships_is_not_also_declared_excluded():
    """The table must not contradict the artifact it describes.

    A name in both places means the declaration is stale -- and a stale declaration is
    worse than none, because it actively asserts something false.
    """
    for name in NOT_PROJECTED:
        assert not (_SHIPPED_SKILLS / name / "SKILL.md").is_file(), (
            f"{name} is declared not-projected and IS projected. The exclusion table "
            "contradicts dist/plugin."
        )


def test_no_canonical_skill_is_silently_missing_from_the_plugin():
    """The property the whole file exists for: absence is never unexplained.

    Every canonical skill directory is either shipped, or declared with a reason. A new
    skill added without either fails here rather than surfacing months later as a review
    finding about a stale projection.
    """
    unexplained = []
    for name in _canonical_skill_dirs():
        shipped = (_SHIPPED_SKILLS / name / "SKILL.md").is_file()
        # Canonical dirs are pack-keyed (`core`) while shipped dirs are skill-id-keyed
        # (`ds-core`); accept either spelling before calling anything missing.
        shipped = shipped or (_SHIPPED_SKILLS / f"ds-{name}" / "SKILL.md").is_file()
        if shipped:
            continue
        if projection_exclusion(name) or projection_exclusion(f"ds-{name}"):
            continue
        unexplained.append(name)
    assert not unexplained, (
        f"canonical skills ship nowhere and declare no reason: {unexplained}. Either "
        "project them, or add them to NOT_PROJECTED with the reason they stay behind."
    )
