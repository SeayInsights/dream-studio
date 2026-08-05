"""R6 — the silent-default / negative-space / fail-quiet review lens.

Captured as a Dream Studio decision in ADR-0002: code that resolves identity/authority/state
by *negative space*, or swallows a correctness-changing failure, silently defaults on the
miss path and produces plausible-but-wrong results that never alert. The lens must live in
BOTH the proactive audit surface (ds-quality:harden) and the review checklist
(ds-core:review) so it is hunted for on the way in and caught on the way through review.
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

    # harden must carry the worked example and cite its Dream Studio ADR (ADR-0002).
    assert "adr-0002" in harden, "harden lens missing the ADR-0002 citation / worked example"

    # The affirmative-refusal remedy — the point of the lens — must be stated, not just the smell.
    assert (
        "negative space" in harden or "negative-space" in harden
    ), "harden lens missing negative-space framing"
    assert "refuse" in harden, "harden lens missing the affirmative refuse-not-default remedy"

    # The lens is Dream Studio's own (ADR-0002) — it must not point at the external repo it
    # was originally studied from. The needle is constructed from fragments so THIS guard file
    # never itself ships that repo's literal name.
    external_repo = "ful" + "crum"
    assert (
        external_repo not in harden
    ), "harden lens must cite the DS ADR-0002, not an external repo"
    assert (
        external_repo not in review
    ), "review lens must cite the DS ADR-0002, not an external repo"
