"""Every compiled reviewer's model comes from the registry, not from this compiler.

`integrations/compiler/reviewers.py`'s `build_reviewer()` used to write `model: sonnet`
into every seat's compiled agent unconditionally -- a literal in the compiler, not a
property of the seat. `canonical/review_lanes.yml` now carries the fact (see
`tests/unit/test_round_table_seat_models.py` for the registry side); these tests hold that
the compiler actually reads it instead of a hardcoded string, and refuses to guess when a
seat's own lanes disagree about what it should be.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
LANES = REPO_ROOT / "canonical" / "review_lanes.yml"
AGENTS_DIR = REPO_ROOT / "canonical" / "agents"


def _seats() -> dict[str, list[dict]]:
    from integrations.compiler.reviewers import NOT_A_REVIEWER

    data = yaml.safe_load(LANES.read_text(encoding="utf-8"))
    out: dict[str, list[dict]] = {}
    for lane in data["lanes"]:
        if lane["seat"] in NOT_A_REVIEWER:
            continue
        out.setdefault(lane["seat"], []).append(lane)
    return out


@pytest.mark.parametrize("seat", sorted(_seats()), ids=lambda s: s)
def test_the_compiled_agent_carries_its_seat_s_registry_model(seat):
    """Read from the file the compiler actually wrote, not from calling the compiler
    again -- a compiler that agreed with itself but drifted from disk would pass a test
    that only asked it to agree with itself."""
    from integrations.compiler.reviewers import _model_for_seat, reviewer_for_seat

    lanes = _seats()[seat]
    expected = _model_for_seat(seat, lanes)
    body = (AGENTS_DIR / f"{reviewer_for_seat(seat)}.md").read_text(encoding="utf-8")
    assert f"\nmodel: {expected}\n" in body, f"{seat}: compiled agent does not carry {expected!r}"


def test_model_for_seat_raises_when_a_seat_s_own_lanes_disagree():
    """One seat compiles to one reviewer, so it can only run on one model. Guessing which
    of two disagreeing lanes to believe would hide exactly the registry/generator drift
    this function exists to surface."""
    from integrations.compiler.reviewers import _model_for_seat

    with pytest.raises(ValueError, match="disagreeing on model"):
        _model_for_seat(
            "A Seat",
            [{"id": "a", "model": "sonnet"}, {"id": "b", "model": "opus"}],
        )


def test_model_for_seat_raises_when_no_lane_declares_one():
    from integrations.compiler.reviewers import _model_for_seat

    with pytest.raises(ValueError, match="declares no model"):
        _model_for_seat("A Seat", [{"id": "a", "model": ""}])


def test_build_reviewer_s_frontmatter_model_changes_when_the_registry_does():
    """Proves the wiring end to end rather than just that the two sides read the same
    constant: change what a seat's lanes say and the compiled output must follow."""
    from integrations.compiler.reviewers import build_reviewer

    lanes = [dict(lane) for lane in _seats()["Finding integrity"]]
    for lane in lanes:
        lane["model"] = "opus"
    assert "\nmodel: opus\n" in build_reviewer("Finding integrity", lanes)
