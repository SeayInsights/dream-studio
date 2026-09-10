"""The round table convenes, and says plainly when it has answered nothing.

Operator instruction, 2026-09-09: "use the round table to review anything before it is
pushed." `canonical/review_lanes.yml` holds the questions and `review_lane_registry` proves
each is answerable — but proving a lane is answerable is not asking it, and the lanes
decided by judgment had nothing surfacing them when a reviewer needed them. No count is
stated: the registry is the count, and a second copy of it here can only drift — which
it already had, reading "three of the six" against eight lanes.

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
    """Named seats rather than the handles these lanes arrived under.

    DERIVED FROM `_SEATS`, NOT RETYPED. This listed the roster literally and had to be
    edited every time a seat was added -- three times in two days -- which is the same
    transcribed-from-the-thing-it-describes defect this file already fixed twice (a seat
    count of 5, a detector count of 3). The property is that every seated lane is held by a
    seat from the CLOSED set, so a lane cannot be filed under a person's name; the roster
    itself lives in one place.
    """
    from core.gates import review_lane_registry

    report = convene(run_detectors=False)
    seats = {seat["seat"] for seat in report["lanes"]}

    assert seats, "no lane was seated"
    assert seats <= review_lane_registry._SEATS, seats - review_lane_registry._SEATS
    # And a seat is a described role, never somebody's handle.
    for seat in seats:
        assert seat.startswith("The "), seat


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

    def _fake(command: str, repo_root=None) -> tuple[bool, str]:
        calls.append(command)
        return (False, "found something") if "untested_fallback" in command else (True, "OK")

    monkeypatch.setattr(round_table, "_run_detector", _fake)
    report = convene(run_detectors=True)

    assert calls, "no detector was run"
    assert report["status"] == "fail", report
    assert "an-untested-fallback-lane" in report["detectors_unclean"], report

    monkeypatch.setattr(round_table, "_run_detector", lambda command, repo_root=None: (True, "OK"))
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
        round_table,
        "_run_detector",
        lambda command, repo_root=None: pytest.fail("budget was not honoured"),
    )

    report = convene(run_detectors=True)

    assert report["status"] == "fail"
    # DERIVED, NOT TRANSCRIBED. This read `== 3`, which is the number of detector lanes
    # the registry happened to hold -- correct today and a false failure the moment a
    # fourth is added. The property is that EVERY detector lane was skipped for budget
    # and every one reported unclean, which is what the assertion actually means.
    detector_lanes = [s["lane"] for s in report["lanes"] if s["kind"] == "detector"]
    assert detector_lanes, "no detector lane was seated"
    assert sorted(report["detectors_unclean"]) == sorted(detector_lanes), report
    for seat in report["lanes"]:
        if seat["kind"] == "detector":
            assert "budget" in seat["detail"], seat


def test_the_seat_column_fits_the_longest_seat():
    """THE INTERPRETER'S SECOND LANE, ASKED OF THIS MODULE AND IT FOUND SOMETHING.

    `_SEAT_WIDTH` was a hardcoded 14 under a comment reading "wide enough for the longest
    seat, so the table reads as a table" -- the promise in prose, kept by nothing. Seating
    "The Interpreter" (15 characters) overflowed it and shifted every question one space
    left. Nothing raised: a misaligned table still looks like a table, which is exactly that
    lane's signature -- a producer grows a vocabulary member and the far end renders it
    wrong instead of refusing it.

    So the width is derived, and this pins the derivation rather than the number. It fails
    for a seat added later without touching the constant, which the constant could not do.
    """
    report = convene(run_detectors=False)
    width = round_table._seat_width(report)

    longest = max(len(seat["seat"]) for seat in report["lanes"])
    assert width >= longest, f"the column truncates {longest}-character seats"

    # And every rendered seat cell really is padded to that width -- deriving the number is
    # no use if the format string still reads the old constant, which is how the constant
    # would have stayed decorative.
    rendered = round_table._render(report)
    for seat in report["lanes"]:
        if seat["kind"] == "detector":
            continue
        assert f"  {seat['seat']:<{width}} {seat['question']}" in rendered, seat["seat"]


def test_a_seat_longer_than_the_floor_still_aligns(monkeypatch):
    """Drives the failure directly, since every seat today happens to fit the derived
    width -- a test that only reads the current registry would pass on the hardcoded
    constant it replaced."""
    report = convene(run_detectors=False)
    report["lanes"] = list(report["lanes"]) + [
        {
            "seat": "The Extremely Long Seat Name",
            "lane": "a-hypothetical-lane",
            "question": "does the column still line up?",
            "signature": "s",
            "kind": "judgment",
            "why": "x" * 40,
        }
    ]

    width = round_table._seat_width(report)
    assert width == len("The Extremely Long Seat Name")

    rendered = round_table._render(report)
    question_columns = {
        line.index("does the column still line up?")
        for line in rendered.splitlines()
        if "does the column still line up?" in line
    }
    warden = [line for line in rendered.splitlines() if line.strip().startswith("The Warden")]
    assert warden, "the Warden's row should be rendered"
    assert question_columns, "the long seat's question should be rendered"
    # The long seat pushed the column out; the Warden's question must move with it.
    assert len(warden[0]) - len(warden[0].lstrip()) == 2
    assert warden[0].index("Two sites") == min(question_columns)


# ── WO 09118a8e: another project convenes its own table ─────────────────────


def _foreign_project(tmp_path, lanes_yaml: str):
    """A second tree with a registry of its own."""
    registry = tmp_path / "canonical" / "review_lanes.yml"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(lanes_yaml, encoding="utf-8")
    return tmp_path


FOREIGN_LANE = """
lanes:
  - id: a-lane-that-exists-only-over-there
    seat: The Warden
    question: >
      Does the other project's own question get asked when its own table convenes?
    signature: >
      A convener that reads its own registry regardless of the tree it was pointed at would
      ask this repository's questions about somebody else's code.
    precedent: >
      WO 09118a8e. The convener resolved the registry from its own tree, so another project
      could only ever be asked dream-studio's questions.
    judgment: true
    why: >
      A fixture lane, present to prove the registry travelled with the tree rather than with
      the convener. It answers nothing about the code under review.
    measurement: >
      Not measured; this lane exists only inside a test fixture and is never registered in
      the shipped registry.
"""


def test_the_table_convenes_against_another_repo(tmp_path):
    """THE POINT OF THE WORK ORDER. The other project's lane is asked, and this repo's are
    not -- which is only provable because the fixture registry differs from the shipped one.
    """
    foreign = _foreign_project(tmp_path, FOREIGN_LANE)

    report = convene(run_detectors=False, repo_root=foreign)
    seated = {seat["lane"] for seat in report["lanes"]}

    assert seated == {"a-lane-that-exists-only-over-there"}, seated
    # And none of this repository's lanes leaked in.
    assert not (seated & _lane_ids()), seated & _lane_ids()


def test_a_project_with_no_registry_raises_rather_than_reporting_a_clean_table(tmp_path):
    """A convening that asked nothing is not a clean review. Reporting an empty table would
    make "this project has no lanes" indistinguishable from "this project passed"."""
    import pytest

    with pytest.raises(FileNotFoundError, match="no review-lane registry"):
        convene(run_detectors=False, repo_root=tmp_path)


def test_a_detector_that_cannot_be_retargeted_is_unclean_not_clean(tmp_path, monkeypatch):
    """THE FAIL-CLOSED PROPERTY, and the reason the whole feature is safe.

    A detector without `--repo-root` exits 2 with "unrecognized arguments". The tempting
    reading -- drop the flag and run anyway -- would scan the convener's own install and
    report that as the other project's result: compared-nothing-reported-clean with an extra
    step. So it is reported as a lane that could not be pointed at the target.
    """
    calls: list[list[str]] = []

    class _Rejected:
        returncode = 2
        stdout = ""
        stderr = "error: unrecognized arguments: --repo-root /somewhere"

    def _fake_run(argv, **kwargs):
        calls.append(argv)
        return _Rejected()

    monkeypatch.setattr(round_table.subprocess, "run", _fake_run)

    clean, detail = round_table._run_detector("py -m core.gates.untested_fallback", tmp_path)
    assert clean is False
    assert "could not be pointed at the target" in detail, detail
    assert "--repo-root" in calls[0], calls[0]


def test_a_same_repo_convening_does_not_pass_the_flag(monkeypatch):
    """Nothing about the existing behaviour changes: the flag is appended only when the
    target differs from the convener's own root, so a lane whose detector predates this work
    still runs here exactly as before."""
    calls: list[list[str]] = []

    class _Ok:
        returncode = 0
        stdout = "fine"
        stderr = ""

    monkeypatch.setattr(
        round_table.subprocess, "run", lambda argv, **k: (calls.append(argv), _Ok())[1]
    )

    round_table._run_detector("py -m core.gates.untested_fallback", round_table.REPO_ROOT)
    assert "--repo-root" not in calls[0], calls[0]


# ── each seat callable on its own ───────────────────────────────────────────


def test_a_single_seat_can_be_convened_and_a_typo_fails():
    """One reviewer type at a time -- and an unknown seat RAISES with the valid set named.

    Silently convening nothing for a typo would report a clean review of everything, which
    is the substitution every lane at this table exists to refuse.
    """
    import pytest

    one = convene(run_detectors=False, seat="The Falsifier")
    seats = {seat["seat"] for seat in one["lanes"]}
    assert seats == {"The Falsifier"}, seats
    assert len(one["lanes"]) < len(convene(run_detectors=False)["lanes"])

    with pytest.raises(KeyError, match="The Warden"):
        convene(run_detectors=False, seat="The Wardn")

    lane = convene(run_detectors=False, lane_id="a-test-that-cannot-fail")
    assert [seat["lane"] for seat in lane["lanes"]] == ["a-test-that-cannot-fail"]

    with pytest.raises(KeyError, match="a-test-that-cannot-fail"):
        convene(run_detectors=False, lane_id="no-such-lane")


def test_every_detector_lane_can_be_pointed_at_another_project():
    """THE GAP THE FAIL-CLOSED PATH FOUND, pinned so it cannot come back.

    Portability was delivered claiming 4 files were the critical path, because
    `event_backed_write.offenders()` already took a `repo_root`. It did -- and its CLI did
    not, so the convener could not point that lane anywhere. It reported "could not be
    pointed at the target tree" rather than scanning its own install and calling another
    project's review clean, which is the safety property working, and it surfaced a wrong
    count instead of hiding it.

    Asserted by DRIVING each detector with the flag rather than by reading its source: a
    grep for "--repo-root" would pass on a module that accepts the flag and ignores it.
    """
    import subprocess
    import sys

    lanes = [
        lane
        for lane in yaml.safe_load(
            (REPO_ROOT / "canonical" / "review_lanes.yml").read_text(encoding="utf-8")
        )["lanes"]
        if "detector" in lane
    ]
    assert lanes, "no detector lane is registered"

    unpointable = []
    for lane in lanes:
        argv = lane["detector"].split()
        if argv and argv[0] in ("py", "python", "python3"):
            argv[0] = sys.executable
        proc = subprocess.run(
            argv + ["--repo-root", str(REPO_ROOT), "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        if "--repo-root" not in (proc.stdout or "") + (proc.stderr or ""):
            unpointable.append(lane["id"])

    assert not unpointable, (
        f"these lanes cannot be pointed at another project: {unpointable}."
        " The convener reports them as unclean rather than scanning its own tree, so a"
        " lane added without the flag makes every foreign convening report a finding."
    )
