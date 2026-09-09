"""The round table convenes, and says plainly when it has answered nothing.

Operator instruction, 2026-09-09: "use the round table to review anything before it is
pushed." `canonical/review_lanes.yml` holds the questions and `review_lane_registry` proves
each is answerable — but proving a lane is answerable is not asking it, and three of the six
are decided by judgment with nothing surfacing them when a reviewer needed them.

THE FIRST CONVENING FOUND A DEFECT IN THE CONVENER. `status` was "pass" whenever no detector
came back unclean — and under `run_detectors=False` no detector is anything, so a caller
reading `status` alone saw a pass from a run that checked nothing. That is the Warden's own
lane (two sites deciding one question, one on a subset of the evidence) landing on the module
that convenes the Warden. It is pinned first below, because a fail-open in a review surface
is worse than the defects the surface exists to find.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.gates import round_table
from core.gates.round_table import convene

REPO_ROOT = Path(__file__).resolve().parents[2]


def _lane_ids() -> set[str]:
    data = yaml.safe_load(
        (REPO_ROOT / "canonical" / "review_lanes.yml").read_text(encoding="utf-8")
    )
    return {lane["id"] for lane in data["lanes"]}


# ── the fail-open the first convening found ─────────────────────────────────


def test_a_listing_that_ran_nothing_is_not_a_pass():
    """THE WARDEN'S LANE, APPLIED TO THE CONVENER, and it found something.

    `--no-detectors` is a listing; the help text says it "answers nothing". Reporting
    `status: pass` for it made "nobody looked" indistinguishable from "nobody found
    anything" — the exact substitution every lane at this table exists to refuse.
    """
    report = convene(run_detectors=False)

    assert report["status"] == "unchecked", report["status"]
    assert report["detectors_run"] == 0
    assert report["detectors_unclean"] == []


def test_the_rendered_listing_says_it_answered_nothing():
    """A human reads the render, not the dict. If the dict is honest and the text is not,
    the text is what misleads."""
    rendered = round_table._render(convene(run_detectors=False))
    assert "UNCHECKED" in rendered
    assert "answers nothing" in rendered


def test_an_unchecked_listing_does_not_fail_the_command():
    """`--no-detectors` is a deliberate listing, so it exits 0 — but the report it prints
    says `unchecked`, which is the distinction that matters."""
    assert round_table.main(["--no-detectors"]) == 0


# ── every seated lane reaches the table ─────────────────────────────────────


def test_every_registered_lane_takes_a_seat():
    """A lane the table does not convene is a lane nobody asks.

    The registry is the source of truth; this asserts the convener reads all of it rather
    than a subset it happened to know about when it was written.
    """
    report = convene(run_detectors=False)
    seated = {seat["lane"] for seat in report["lanes"]}
    assert seated == _lane_ids(), _lane_ids() ^ seated


def test_a_graded_lane_arrives_with_its_question_and_fixture():
    """The whole point of surfacing a judgment lane: the reviewer gets the question and the
    fixture that teaches the shape, not just a lane id."""
    report = convene(run_detectors=False)
    graded = [seat for seat in report["lanes"] if seat["kind"] == "graded"]

    assert graded, "no graded lane was seated"
    for seat in graded:
        assert seat["question"].endswith("?"), seat
        assert seat["fixture"].startswith("tests/evals/"), seat
        assert (REPO_ROOT / seat["fixture"]).is_file(), seat["fixture"]


def test_a_declared_judgment_lane_arrives_with_what_is_missing():
    report = convene(run_detectors=False)
    declared = [seat for seat in report["lanes"] if seat["kind"] == "judgment"]

    assert declared, "no declared-judgment lane was seated"
    for seat in declared:
        assert len(seat["why"]) >= 40, seat


def test_the_seats_are_the_round_table():
    """Named seats rather than the handles these lanes arrived under."""
    report = convene(run_detectors=False)
    seats = {seat["seat"] for seat in report["lanes"]}
    assert seats == {"The Warden", "The Machinist", "The Archivist", "The Surveyor", "The Herald"}


# ── a detector that cannot run is not a detector that found nothing ─────────


def test_a_detector_that_cannot_be_run_is_reported_unclean():
    """Fail closed. Silence from a check that never ran is indistinguishable from a clean
    result, which is the shape `core/gates/fail_open_probe.py` exists for."""
    clean, detail = round_table._run_detector("py -m core.gates.no_such_detector_module")
    assert clean is False
    assert detail

    clean, detail = round_table._run_detector("this-is-not-an-executable-at-all")
    assert clean is False
    assert "could not run" in detail


def test_a_detector_lane_is_reported_from_its_exit_status(monkeypatch):
    """Drives `convene` with a stubbed runner rather than spending 30s on three real
    detectors, and asserts BOTH directions -- otherwise a convener that always reported
    clean would satisfy the pass case."""
    calls: list[str] = []

    def _fake(command: str) -> tuple[bool, str]:
        calls.append(command)
        return (False, "found something") if "untested_fallback" in command else (True, "OK")

    monkeypatch.setattr(round_table, "_run_detector", _fake)
    report = convene(run_detectors=True)

    assert calls, "no detector was run"
    assert report["status"] == "fail", report
    assert "an-untested-fallback-lane" in report["detectors_unclean"], report

    monkeypatch.setattr(round_table, "_run_detector", lambda command: (True, "OK"))
    assert convene(run_detectors=True)["status"] == "pass"


def test_the_table_stops_at_its_own_budget(monkeypatch):
    """THE MACHINIST'S LANE, APPLIED TO THE CONVENER. Each detector is bounded at 600s and
    nothing bounded the total; the registry is authored rather than data-driven, so the
    count is small today -- and "small today" is what that lane refuses.

    A lane skipped for budget is reported UNCLEAN, not clean, for the same reason a detector
    that cannot run is.
    """
    monkeypatch.setattr(round_table, "_TABLE_BUDGET_S", -1.0)
    monkeypatch.setattr(
        round_table, "_run_detector", lambda command: pytest.fail("budget was not honoured")
    )

    report = convene(run_detectors=True)

    assert report["status"] == "fail"
    assert len(report["detectors_unclean"]) == 3, report["detectors_unclean"]
    for seat in report["lanes"]:
        if seat["kind"] == "detector":
            assert "budget" in seat["detail"], seat
