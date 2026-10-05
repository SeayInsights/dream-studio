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


@pytest.fixture
def isolated_seat_pin_home(tmp_path, monkeypatch):
    """Seat-provider pins (core.config.seat_providers) live in config.json under
    DREAM_STUDIO_HOME -- isolated to a per-test tmp dir so setting one here cannot leak
    into this developer's real ~/.dream-studio or into another test in this session
    (conftest.py sets DREAM_STUDIO_HOME once, session-wide). Same approach
    test_seat_pin_installer_routing.py's isolated_ds_home fixture uses."""
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(tmp_path / "ds-home"))


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
    # No repo_root: every seat here is Dream Studio's own, so AGENTS_DIR always answers.
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


# ── resolve_live_model: the dispatch-time counterpart of resolve_seat_assignment ────
#
# resolve_seat_assignment(seat, install_target) answers "what does this seat compile
# onto" -- a compile/install-time question with an install_target that has no meaning
# for a live round (core.work_orders.review_answers.dispatch_review_round installs
# nothing). resolve_live_model(seat, lanes) answers the narrower live-dispatch question
# -- which model, never which tool -- consulting the SAME pin store.


def test_resolve_live_model_falls_back_to_the_registry_with_no_pin(isolated_seat_pin_home):
    from integrations.compiler.reviewers import resolve_live_model

    assert resolve_live_model("A Seat", [{"id": "a", "model": "haiku"}]) == "haiku"


def test_resolve_live_model_prefers_a_pins_model_over_the_registry(isolated_seat_pin_home):
    from core.config import seat_providers
    from integrations.compiler.reviewers import resolve_live_model

    seat_providers.set_seat_provider("A Seat", provider="claude_code", model="opus")
    assert resolve_live_model("A Seat", [{"id": "a", "model": "haiku"}]) == "opus"


def test_resolve_live_model_defers_to_the_registry_when_the_pin_names_no_model(
    isolated_seat_pin_home,
):
    """A pin can set only a provider (or provider+effort) and leave model unset --
    resolve_seat_assignment already defers that to _model_for_seat() at compile time;
    the live reader must defer identically, not treat an unset model as a pin to
    nothing."""
    from core.config import seat_providers
    from integrations.compiler.reviewers import resolve_live_model

    seat_providers.set_seat_provider("A Seat", provider="codex")
    assert resolve_live_model("A Seat", [{"id": "a", "model": "haiku"}]) == "haiku"


def test_resolve_live_model_raises_when_the_seats_own_lanes_disagree(isolated_seat_pin_home):
    """Same refusal _model_for_seat() makes, reached through the pin-aware wrapper when
    there is no pin to short-circuit it."""
    from integrations.compiler.reviewers import resolve_live_model

    with pytest.raises(ValueError, match="disagreeing on model"):
        resolve_live_model("A Seat", [{"id": "a", "model": "sonnet"}, {"id": "b", "model": "opus"}])
