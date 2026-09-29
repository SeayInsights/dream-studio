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


def _seats(include_chair: bool = False) -> dict[str, list[dict]]:
    """Seats that get a reviewer.

    The chair is excluded. Its lane asks what the single merge recommendation is and
    whether every finding's severity is calibrated against it — answerable only by
    whoever holds the other verdicts, which a subagent never does. The lane stays on the
    bench; what it does not get is a specialist, because the caller IS the chair.
    """
    from integrations.compiler.reviewers import NOT_A_REVIEWER

    data = yaml.safe_load(LANES.read_text(encoding="utf-8"))
    out: dict[str, list[dict]] = {}
    for lane in data["lanes"]:
        if not include_chair and lane["seat"] in NOT_A_REVIEWER:
            continue
        out.setdefault(lane["seat"], []).append(lane)
    return out


SEATS = _seats()


def test_the_bench_is_populated():
    """Guard the guard: an empty registry would make every parametrised case below
    vacuous, which is the failure this whole bench exists to catch. D13 collapsed 19 seats
    to 10 — nine of which take a reviewer."""
    assert len(SEATS) >= 8, f"only {len(SEATS)} seats — has the registry been truncated?"
    assert sum(len(v) for v in SEATS.values()) >= 20, "lanes were lost in a merge"


def test_the_chair_has_no_reviewer():
    """A subagent sees its own lanes and nothing else, so an agent here would be asked to
    reconcile findings it was never given."""
    from integrations.compiler.reviewers import NOT_A_REVIEWER, reviewer_for_seat

    assert "Chair and verdict owner" in NOT_A_REVIEWER
    for seat in NOT_A_REVIEWER:
        assert reviewer_for_seat(seat) is None, f"{seat} was given a reviewer"


def test_no_seat_carries_only_one_lane_except_the_chair():
    """What D13 was for. Fifteen of nineteen seats carried exactly one lane — not fifteen
    specialists, a list of questions with a name attached to each — and six of those were
    the same stance on different surfaces, so three agents opened the same diff to ask
    three neighbouring questions and none saw the case between them."""
    singles = [seat for seat, lanes in SEATS.items() if len(lanes) == 1]
    assert not singles, f"seats still carrying one lane: {singles}"


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
    } - {None}
    missing = expected - convened
    assert not missing, f"seats convened nothing: {sorted(missing)}\n{output[-2000:]}"
    assert len(expected) >= 8, f"only {len(expected)} seats need judgment — check the registry"


def test_a_seat_with_no_compiled_reviewer_names_nothing():
    """Fails to None rather than to a guess. A round table pointing at an agent that does
    not exist is the dangling-instruction shape the instruction-commands gate refuses."""
    from integrations.compiler.reviewers import reviewer_for_seat

    assert reviewer_for_seat("A Seat That Does Not Exist") is None


# --------------------------------------------------------------------------
# A project's own seat (core.work_orders.project_review_lanes) gets named too
# --------------------------------------------------------------------------
#
# Installing a project's compiled seat onto a tool does not by itself let convene()
# name a reviewer for it: reviewer_for_seat() only ever checked Dream Studio's own
# AGENTS_DIR. Without this, a project's own seat sat in `unreviewed` forever, next to
# the chair -- a seat with a real compiled agent, reported as if it had none.

_PROJECT_LANE_YAML = """
mode: add
lanes:
  - id: a-project-specific-lane
    seat: PCI Scope
    question: >
      Does this change touch anything in the cardholder data environment?
    signature: >
      A file under payments/ or checkout/ changed with no PCI reviewer sign-off noted
      in the PR body.
    precedent: >
      Filed after an internal audit found three merged PRs touching payment capture
      with no compliance review recorded anywhere.
    measurement: >
      No automatable predicate exists for "touches CDE" without a maintained
      file-ownership map, so this is judgment rather than a detector.
    model: sonnet
    judgment: true
    why: >
      No maintained CDE file-ownership map exists yet to turn this into a detector.
"""


def _write_project_marker(tmp_path, body: str = _PROJECT_LANE_YAML):
    (tmp_path / ".ds-review-lanes.yml").write_text(body, encoding="utf-8")


def test_a_projects_own_seat_is_named_with_repo_root(tmp_path):
    from integrations.compiler.reviewers import _slug, reviewer_for_seat

    _write_project_marker(tmp_path)

    assert reviewer_for_seat("PCI Scope", repo_root=tmp_path) == _slug("PCI Scope")


def test_without_repo_root_a_projects_own_seat_is_still_unnamed(tmp_path):
    """The parameter is opt-in. A caller that does not pass repo_root gets today's exact
    behavior -- no project seat reachable, same as before this feature existed."""
    from integrations.compiler.reviewers import reviewer_for_seat

    _write_project_marker(tmp_path)

    assert reviewer_for_seat("PCI Scope") is None


def test_a_projects_own_seat_is_rendered_into_a_local_cache(tmp_path):
    from integrations.compiler.reviewers import (
        _PROJECT_REVIEWER_CACHE,
        _slug,
        build_reviewer,
        group_by_seat,
        reviewer_for_seat,
    )
    from core.work_orders.project_review_lanes import load_and_validate

    _write_project_marker(tmp_path)
    reviewer_for_seat("PCI Scope", repo_root=tmp_path)

    cache_path = Path(tmp_path).joinpath(*_PROJECT_REVIEWER_CACHE, f"{_slug('PCI Scope')}.md")
    assert cache_path.is_file()

    _mode, lanes = load_and_validate(tmp_path)
    expected = build_reviewer("PCI Scope", group_by_seat(lanes)["PCI Scope"])
    assert cache_path.read_text(encoding="utf-8") == expected


def test_the_cache_regenerates_when_the_marker_s_content_changes(tmp_path):
    from integrations.compiler.reviewers import _PROJECT_REVIEWER_CACHE, _slug, reviewer_for_seat

    _write_project_marker(tmp_path)
    reviewer_for_seat("PCI Scope", repo_root=tmp_path)
    cache_path = Path(tmp_path).joinpath(*_PROJECT_REVIEWER_CACHE, f"{_slug('PCI Scope')}.md")
    first = cache_path.read_text(encoding="utf-8")

    _write_project_marker(tmp_path, _PROJECT_LANE_YAML.replace("model: sonnet", "model: opus"))
    reviewer_for_seat("PCI Scope", repo_root=tmp_path)
    second = cache_path.read_text(encoding="utf-8")

    assert first != second
    assert "model: opus" in second


def test_one_of_dream_studios_own_seats_never_touches_the_project_cache(tmp_path):
    """The short-circuit: a seat AGENTS_DIR already answers must never fall through to
    the project-cache path, even with a marker present and repo_root given."""
    from integrations.compiler.reviewers import _PROJECT_REVIEWER_CACHE, reviewer_for_seat

    _write_project_marker(tmp_path)
    reviewer_for_seat("Finding integrity", repo_root=tmp_path)  # a real Dream Studio seat

    assert not (Path(tmp_path) / _PROJECT_REVIEWER_CACHE[0]).exists()


def test_a_repo_root_with_no_marker_names_nothing_for_an_unknown_seat(tmp_path):
    from integrations.compiler.reviewers import reviewer_for_seat

    assert reviewer_for_seat("Not A Real Seat At All", repo_root=tmp_path) is None


def test_convene_names_a_real_reviewer_for_a_projects_own_seat(tmp_path):
    """The end-to-end proof: convene() against a marker'd project returns a reviewer
    slug for the project's own lane, and assignments() files it as a real assignment --
    not under `unreviewed`, next to the chair, which is where it sat before this."""
    from core.gates.round_table import assignments, convene

    _write_project_marker(tmp_path)

    report = convene(run_detectors=False, repo_root=tmp_path)
    entry = next(s for s in report["lanes"] if s["lane"] == "a-project-specific-lane")
    assert entry["reviewer"], "the project's own seat was named nothing"

    grouped = assignments(report)
    reviewers = {a["reviewer"] for a in grouped if a["reviewer"]}
    assert entry["reviewer"] in reviewers

    unreviewed_seats = {a["seat"] for a in grouped if not a["reviewer"]}
    assert "PCI Scope" not in unreviewed_seats
