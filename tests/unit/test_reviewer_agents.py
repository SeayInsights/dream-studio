"""Every review seat has a reviewer that can answer it.

`canonical/review_lanes.yml` is the bench: 26 lanes across 19 seats, each lane a repeatable
question with the defect signature it catches, a precedent it came from, and the
measurement that decided how it is answered.

**Nineteen of the twenty-six are `judgment: true`** — no detector, no eval. What the round
table did with them was print `19 lane(s) need a person` and stop. The seats are
specialists and nothing specialist answered them, so one generalist answered all nineteen
or nobody did.

A judgment lane is exactly what a subagent is for, and the lane already carries everything
such an agent needs. These tests hold three things: a reviewer exists for every seat, it
carries that seat's own lanes and nobody else's, and the round table names it rather than
asking the room.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
LANES = REPO_ROOT / "canonical" / "review_lanes.yml"
AGENTS_DIR = REPO_ROOT / "canonical" / "agents"


def _seats() -> dict[str, list[dict]]:
    data = yaml.safe_load(LANES.read_text(encoding="utf-8"))
    out: dict[str, list[dict]] = {}
    for lane in data["lanes"]:
        out.setdefault(lane["seat"], []).append(lane)
    return out


SEATS = _seats()


def test_the_bench_is_populated():
    """Guard the guard: an empty registry would make every parametrised case below
    vacuous, which is the failure this whole bench exists to catch."""
    assert len(SEATS) >= 15, f"only {len(SEATS)} seats — has the registry been truncated?"


@pytest.mark.parametrize("seat", sorted(SEATS), ids=lambda s: s)
def test_every_seat_has_a_reviewer(seat):
    from integrations.compiler.reviewers import reviewer_for_seat

    name = reviewer_for_seat(seat)
    assert name, f"the {seat!r} seat has no compiled reviewer"
    assert (AGENTS_DIR / f"{name}.md").is_file()


@pytest.mark.parametrize("seat", sorted(SEATS), ids=lambda s: s)
def test_a_reviewer_carries_its_own_lanes_and_no_others(seat):
    """The bench works because each seat asks its own question. A reviewer holding another
    seat's lane would answer it twice over, or absorb a concern that should have been
    handed back by name."""
    from integrations.compiler.reviewers import reviewer_for_seat

    body = (AGENTS_DIR / f"{reviewer_for_seat(seat)}.md").read_text(encoding="utf-8")
    mine = {lane["id"] for lane in SEATS[seat]}
    for lane_id in mine:
        assert f"`{lane_id}`" in body, f"{seat}: missing its own lane {lane_id}"

    others = {lane["id"] for other, lanes in SEATS.items() if other != seat for lane in lanes}
    for lane_id in others - mine:
        assert f"## `{lane_id}`" not in body, f"{seat} carries {lane_id}, which is not its lane"


@pytest.mark.parametrize("seat", sorted(SEATS), ids=lambda s: s)
def test_a_reviewer_carries_the_question_itself_not_just_the_lane_id(seat):
    """An id is a label. The question, the signature and the precedent are what let a
    reviewer recognise the defect, and they are already written in the registry."""
    from integrations.compiler.reviewers import reviewer_for_seat

    body = (AGENTS_DIR / f"{reviewer_for_seat(seat)}.md").read_text(encoding="utf-8")
    for lane in SEATS[seat]:
        question = " ".join(str(lane["question"]).split())
        assert question in " ".join(body.split()), f"{seat}: lane {lane['id']} lost its question"


@pytest.mark.parametrize("seat", sorted(SEATS), ids=lambda s: s)
def test_a_reviewer_states_what_it_returns(seat):
    """A reviewer's verdict is the only thing that survives it. Without a fixed shape the
    chair cannot assemble the answers, and `cannot-tell` — the answer that keeps a lane
    honest when the evidence is absent — has nowhere to go."""
    from integrations.compiler.reviewers import reviewer_for_seat

    body = (AGENTS_DIR / f"{reviewer_for_seat(seat)}.md").read_text(encoding="utf-8")
    assert "## What you return" in body
    assert "cannot-tell" in body, f"{seat}: no way to report that the evidence was absent"


def test_the_reviewers_match_the_registry():
    """The drift half. A lane edited without recompiling leaves a reviewer asking the
    previous version of the question, which is worse than asking none."""
    from integrations.compiler.reviewers import check

    stale = check()
    assert not stale, (
        f"{len(stale)} reviewer(s) no longer match their seat: {', '.join(stale)}. "
        "Run `py -m integrations.compiler.reviewers --write`."
    )


def test_a_seat_removed_from_the_registry_loses_its_reviewer(tmp_path, monkeypatch):
    """Drift runs backwards too: a reviewer for a seat nobody registers any more is an
    agent asking a question the bench retired."""
    import integrations.compiler.reviewers as rev

    fake_agents = tmp_path / "agents"
    fake_agents.mkdir()
    orphan = fake_agents / f"{rev.PREFIX}a-seat-that-was-removed.md"
    orphan.write_text("stale", encoding="utf-8")

    monkeypatch.setattr(rev, "AGENTS_DIR", fake_agents)
    rev.write()
    assert not orphan.exists(), "a retired seat kept its reviewer"


# --------------------------------------------------------------------------
# The wiring: the round table names what to convene
# --------------------------------------------------------------------------


def test_the_round_table_names_a_reviewer_for_every_judgment_lane():
    """It used to end at "N lane(s) need a person" — a specialist question handed to
    whoever happened to be reading. Asserting on the rendered output rather than on the
    data, because a field nobody prints is the defect this repository keeps paying for."""
    import subprocess
    import sys

    done = subprocess.run(
        [sys.executable, "-m", "core.gates.round_table", "--all", "--no-detectors"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )
    output = done.stdout + done.stderr
    assert "ASKED OF YOU" in output, f"the listing changed shape\n{output[-2000:]}"
    assert (
        "need a person" not in output
    ), "the round table still hands its specialist questions to the room"

    convened = set(re.findall(r"convene: (review-[a-z0-9-]+)", output))
    from integrations.compiler.reviewers import reviewer_for_seat

    # Only seats with a lane a detector cannot decide appear under ASKED OF YOU. A seat
    # whose every lane runs mechanically has nothing to convene anyone for, and expecting
    # it here would be the test demanding the listing be wrong. It still HAS a reviewer,
    # which the parametrised cases above cover — it just is not asked for here.
    expected = {
        reviewer_for_seat(seat)
        for seat, lanes in SEATS.items()
        if any(not lane.get("detector") for lane in lanes)
    }
    missing = expected - convened
    assert not missing, f"seats convened nothing: {sorted(missing)}\n{output[-2000:]}"
    assert len(expected) >= 15, f"only {len(expected)} seats need judgment — check the registry"


def test_a_seat_with_no_compiled_reviewer_names_nothing():
    """Fails to None rather than to a guess. A round table pointing at an agent that does
    not exist is the dangling-instruction shape the instruction-commands gate refuses."""
    from integrations.compiler.reviewers import reviewer_for_seat

    assert reviewer_for_seat("A Seat That Does Not Exist") is None
