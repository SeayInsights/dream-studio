"""R6 — the silent-default / negative-space / fail-quiet review lens.

Derived from Fulcrum ADR-004 (token classes & affirmative sender attribution): code that
resolves identity/authority/state by *negative space* and silently defaults on the miss
path produces plausible-but-wrong results that never alert. The lens must live in BOTH the
proactive audit surface (ds-quality:harden) and the review checklist (ds-core:review) so it
is hunted for on the way in and caught on the way through review.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HARDEN = REPO / "canonical" / "skills" / "quality" / "modes" / "harden" / "SKILL.md"
REVIEW = REPO / "canonical" / "skills" / "core" / "modes" / "review" / "SKILL.md"


def test_silent_default_lens_present():
    harden = HARDEN.read_text(encoding="utf-8").lower()
    review = REVIEW.read_text(encoding="utf-8").lower()

    # The lens marker must appear in both surfaces.
    assert "silent-default" in harden, "harden SKILL.md missing the silent-default lens"
    assert "silent-default" in review, "review SKILL.md missing the silent-default lens"

    # harden must carry the ADR-004 worked example (AC: "with the ADR-004 example pattern").
    assert "adr-004" in harden, "harden lens missing the ADR-004 example"

    # The affirmative-refusal remedy — the point of the lens — must be stated, not just the smell.
    assert (
        "negative space" in harden or "negative-space" in harden
    ), "harden lens missing negative-space framing"
    assert "refuse" in harden, "harden lens missing the affirmative refuse-not-default remedy"
