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
    # all_seats, because lanes now fire on relevance to the change set; the claim here
    # is that the convener reads the WHOLE registry, not that every lane is relevant.
    report = convene(run_detectors=False, all_seats=True)
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
    # And a seat is a described role, never somebody's handle. The old convention was a
    # "The X" prefix; the roster retired that for functional names, so the property is
    # asserted directly instead of through the prefix that used to imply it.
    for seat in seats:
        assert seat == seat.strip() and len(seat) > 3, seat
        assert not seat.startswith("@"), seat
        assert " " in seat, f"a seat names a function, not a single word: {seat}"


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
        # AN ABSTAINING SEAT RENDERS ITS REASON, NOT ITS QUESTION -- it is seated with
        # nothing to judge yet, so no question is put to the reader. Still checked for
        # padding here rather than skipped: excluding it from the alignment test is how a
        # column would quietly stop fitting the longest seat, which is the one that
        # abstains.
        cell = seat.get("abstained_why") if seat.get("abstained") else seat["question"]
        assert f"  {seat['seat']:<{width}} {cell}" in rendered, seat["seat"]


def test_a_seat_longer_than_the_floor_still_aligns(monkeypatch):
    """Drives the failure directly, since every seat today happens to fit the derived
    width -- a test that only reads the current registry would pass on the hardcoded
    constant it replaced."""
    report = convene(run_detectors=False, all_seats=True)
    report["lanes"] = list(report["lanes"]) + [
        {
            "seat": "An Extremely Long Seat Name That Outgrows Every Real One",
            "lane": "a-hypothetical-lane",
            "question": "does the column still line up?",
            "signature": "s",
            "kind": "judgment",
            "why": "x" * 40,
        }
    ]

    width = round_table._seat_width(report)
    assert width == len("An Extremely Long Seat Name That Outgrows Every Real One")

    rendered = round_table._render(report)
    question_columns = {
        line.index("does the column still line up?")
        for line in rendered.splitlines()
        if "does the column still line up?" in line
    }
    # Derived, not named: hardcoding a seat here is how this test rotted the last time
    # the roster changed. Any real judgment seat proves the column moved with it.
    real_seat = next(
        s["seat"]
        for s in report["lanes"]
        if s["kind"] != "detector" and s["lane"] != "a-hypothetical-lane"
    )
    warden = [line for line in rendered.splitlines() if line.strip().startswith(real_seat)]
    assert warden, f"{real_seat}'s row should be rendered"
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

    one = convene(run_detectors=False, seat="Test-integrity inquisitor")
    seats = {seat["seat"] for seat in one["lanes"]}
    assert seats == {"Test-integrity inquisitor"}, seats
    assert len(one["lanes"]) < len(convene(run_detectors=False, all_seats=True)["lanes"])

    with pytest.raises(KeyError, match="Gate-integrity engineer"):
        convene(run_detectors=False, seat="Gate-integrity enginer")

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


# ── WO 09118a8e task 3: the table ships, and says what it could not check ───


def _fake_install(tmp_path):
    """A plugin-shaped install: `review/` only, no `core.gates` anywhere."""
    import shutil
    import subprocess

    review = tmp_path / "review"
    review.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO_ROOT / "canonical" / "review_lanes.yml", review / "review_lanes.yml")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, timeout=120)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, timeout=120)
    return tmp_path


def test_an_install_without_the_repo_can_still_convene(tmp_path):
    """THE POINT OF THE TASK. `dist/plugin` shipped agents and skills only, so an install
    got the lanes as PROSE in a projected SKILL.md -- guidance where a rule belongs, for
    that project.

    The registry now travels in `review/review_lanes.yml`, and `registry_for` finds either
    layout. Asserted by resolving against a tree that has ONLY the shipped layout, so a
    convener still reading `canonical/` would fail here.
    """
    install = _fake_install(tmp_path)

    resolved = round_table.registry_for(install)
    assert resolved.name == "review_lanes.yml"
    assert resolved.parent.name == "review", resolved
    assert resolved.is_file()

    report = convene(run_detectors=False, repo_root=install, all_seats=True)
    assert {seat["lane"] for seat in report["lanes"]} == _lane_ids()


def test_the_source_layout_wins_when_both_exist(tmp_path):
    """A developer in the repo must be asked the repo's LIVE questions, not a stale copy
    inside `dist/`. Both layouts present, canonical chosen."""
    install = _fake_install(tmp_path)
    canonical = install / "canonical"
    canonical.mkdir(parents=True, exist_ok=True)
    (canonical / "review_lanes.yml").write_text("lanes: []\n", encoding="utf-8")

    resolved = round_table.registry_for(install)
    assert resolved.parent.name == "canonical", resolved


def test_a_detector_that_is_not_installed_reports_unrun_not_found(monkeypatch, tmp_path):
    """THE HALF THAT MATTERS MORE THAN THE COPYING.

    In a skills-only install none of the detector lanes can run -- they are
    `py -m core.gates.<module>` and that package is not there. An unrunnable detector used
    to render as [FOUND], so such an install would report FOUR FINDINGS WHERE THERE ARE
    NONE: the Interpreter's own lane, a value (could not run) displayed as another value's
    meaning (a defect), and the same shape as `not_applicable` drawn as 0% uptime.

    THE VERDICT STAYS FAIL-CLOSED and only the rendering changes -- a review whose
    detectors could not run is not a clean review, and weakening that would recreate the
    fail-open the three-state `status` exists to close.
    """
    clean, detail = round_table._run_detector("py -m core.gates.no_such_detector_at_all")

    assert clean is False, "still not clean -- fail-closed is the point"
    assert detail.startswith(round_table._UNRUNNABLE), detail
    assert "not installed here" in detail

    # AND THE RENDER IS DRIVEN WITH A REAL UNRUNNABLE DETECTOR, not a hand-built report.
    #
    # Two earlier attempts were wrong in instructive ways. The first mutated seats and left
    # `status` at "unchecked", so it never reached the branch it asserted on -- a report
    # constructed to match its own assertion. The second convened against a fake install and
    # expected the detectors to be missing, but pytest runs INSIDE this repo, so
    # `core.gates` is importable and the subprocesses genuinely ran and reported clean. The
    # skills-only condition was verified by hand from a clean working directory; it cannot
    # be reproduced from a test that has the package on its path without rewriting the
    # child environment. So the lane registry is replaced with one pointing at a module
    # that really does not exist, which exercises the same code path honestly.
    monkeypatch.setattr(
        round_table,
        "_lanes",
        lambda repo_root=None: [
            {
                "id": "a-lane-whose-detector-is-absent",
                "seat": "The Machinist",
                "question": "does an absent detector read as a finding?",
                "signature": "s",
                "detector": "py -m core.gates.no_such_detector_at_all",
            }
        ],
    )
    report = convene(run_detectors=True)
    assert report["status"] == "fail", "a review whose detectors could not run is not clean"
    assert all(
        seat.get("unrunnable") for seat in report["lanes"] if seat["kind"] == "detector"
    ), report["lanes"]
    rendered = round_table._render(report)
    assert "[UNRUN]" in rendered
    assert "[FOUND]" not in rendered, rendered
    assert "COULD NOT BE CHECKED" in rendered
    assert "Not findings" in rendered


def test_a_real_finding_still_reports_found(monkeypatch):
    """The other direction, and without it the fix would be indistinguishable from
    relabelling every failure as unrunnable."""
    monkeypatch.setattr(
        round_table,
        "_run_detector",
        lambda command, repo_root=None: (False, "found something real"),
    )
    rendered = round_table._render(convene(run_detectors=True))
    assert "[FOUND]" in rendered
    assert "found something" in rendered
    assert "[UNRUN]" not in rendered, rendered


# ── WO d0658106: the table is convened, not merely registered ──────────────────


def test_a_change_set_that_edits_the_table_is_flagged_as_self_review():
    """The table judging its own definition must say so.

    When the change set edits `canonical/review_lanes.yml` or this module, the lens and
    the subject are the same artifact -- a reviewer grading its own rubric. That is not a
    reason to skip the review, but leaving it unsaid lets the report be read as
    independent when it is not. The Grader-integrity seat refuses exactly this shape
    elsewhere; it has to hold when the seat is looking at itself.
    """
    report = convene(run_detectors=False, paths=["canonical/review_lanes.yml", "README.md"])

    assert report["self_review"] == ["canonical/review_lanes.yml"]
    rendered = round_table._render(report)
    assert "SELF-REVIEW" in rendered
    assert "canonical/review_lanes.yml" in rendered


def test_a_change_set_that_leaves_the_table_alone_is_not_flagged():
    """The negative case, without which the flag could be unconditional."""
    report = convene(run_detectors=False, paths=["core/work_orders/close.py"])

    assert report["self_review"] == []
    assert "SELF-REVIEW" not in round_table._render(report)


def test_the_reviewers_reviewer_abstains_rather_than_passing_vacuously():
    """The one seat with no input on a first pass must not read as a lane with no issues.

    It audits other seats' findings, and on a first convening there are none. Asking the
    question would put an unanswerable lane in front of a reader; answering it would be a
    pass over an empty set. "Looked and found nothing" and "had nothing to look at" are
    different answers, and only one of them is reassuring.
    """
    report = convene(run_detectors=False, all_seats=True)

    seat = next(ln for ln in report["lanes"] if ln["lane"] == "reviewer-s-reviewer")
    assert seat.get("abstained") is True
    assert "no prior verdict" in seat.get("abstained_why", "")

    # And it is NOT counted among the questions a person still owes an answer to.
    assert "reviewer-s-reviewer" not in report["awaiting_judgment"]
    assert "reviewer-s-reviewer" in report["abstained"]

    rendered = round_table._render(report)
    assert "ABSTAINED" in rendered


def test_the_reviewers_reviewer_takes_its_seat_once_there_are_findings():
    """The abstention is conditional on having nothing to re-check, not permanent.

    Without this, `abstained = True` hardcoded would satisfy the test above forever and
    the seat would never sit -- a lane that can only abstain is a lane that was removed.
    """
    report = convene(
        run_detectors=False,
        all_seats=True,
        prior_findings=[{"title": "a finding from the previous pass"}],
    )

    seat = next(ln for ln in report["lanes"] if ln["lane"] == "reviewer-s-reviewer")
    assert not seat.get("abstained"), "with a prior finding to re-check, the seat must sit"
    assert "reviewer-s-reviewer" in report["awaiting_judgment"]


def test_the_table_reports_its_own_reach_rather_than_hanging_it_on_a_lane():
    """Attribution reach qualifies the TABLE, and used to ride on branch-freshness.

    `attribution_reach()` counts how many open work orders declare a module boundary an
    edit can be attributed to. It was attached to the `a-branch-behind-its-base` lane,
    whose question is how many commits behind its base a branch is -- a number it
    qualifies in no way. An honestly computed value reported against the wrong question is
    the Observability seat's own signature, and it was on this module.
    """
    report = convene(run_detectors=False, all_seats=True)

    assert "attribution_reach" in report, "the table's reach belongs to the table"
    for lane in report["lanes"]:
        assert (
            "attribution_reach" not in lane
        ), f"{lane['lane']} carries a reach number that says nothing about its question"


def test_the_verdict_records_which_lanes_were_convened(tmp_path, monkeypatch):
    """verify() must convene the table, and the verdict must name what it convened.

    THE DEFECT: `convene()` had two callers, its own CLI and its own test. A verdict
    carried scores and named no lens, so one produced against the whole bench and one
    produced with the table never opened were indistinguishable to `independent_review`.

    Driven through the REAL `verify_work_order` with canned graders rather than asserted
    against the source text -- a grep for `convene(` would pass on a call that raises and
    is swallowed, which is the failure mode most likely to actually happen here.
    """
    import uuid as _uuid

    from tests.unit.test_verify_authority_gate import (
        _make_db,
        _make_git_repo,
        _patch_db,
        _seed_wo,
    )

    monkeypatch.setenv("DREAM_STUDIO_VERIFY_MOCK", "1")
    repo = _make_git_repo(tmp_path, ["chore: unrelated"])
    db_path = _make_db(tmp_path)
    wo_id = str(_uuid.uuid4())
    _seed_wo(db_path, work_order_id=wo_id, title="WO-TABLE - x", ac="SQL-CHECK: SELECT 1")
    monkeypatch.setattr("core.work_orders.verify_git._collect_git_commits", lambda *a, **k: None)

    with _patch_db(db_path):
        from core.work_orders.verify import verify_work_order

        result = verify_work_order(
            work_order_id=wo_id,
            source_root=repo,
            dream_studio_home=tmp_path,
            planning_root=tmp_path / "planning",
        )

    table = result.get("round_table")
    assert table is not None, "the verdict must carry a round-table section, never omit it"
    assert table.get("seats"), (
        "verify convened no lane. A verdict with no lens is a score with no provenance, "
        f"and independent_review now refuses it. Section was: {table}"
    )
    seat = table["seats"][0]
    assert {"seat", "lane", "kind"} <= set(seat), f"a recorded seat must be identifiable: {seat}"
    assert table.get("status") in {"pass", "fail", "unchecked", "unavailable"}


def test_an_attestation_declares_that_it_convened_nothing(tmp_path, monkeypatch):
    """The sibling path, which convenes no table ON PURPOSE.

    `ds work-order attest` is a person certifying work with no machine-traceable
    evidence -- there is no diff for a lane to be relevant to. But a MISSING key would be
    indistinguishable from a verdict written before the table existed, and the close gate
    has to tell those apart. The absence is declared rather than left blank.
    """
    import json as _json
    import uuid as _uuid

    from tests.unit.test_verify_authority_gate import _make_db, _make_git_repo, _patch_db, _seed_wo

    repo = _make_git_repo(tmp_path, ["chore: unrelated"])
    db_path = _make_db(tmp_path)
    wo_id = str(_uuid.uuid4())
    _seed_wo(db_path, work_order_id=wo_id, title="WO-ATTEST - x", ac=None)

    with _patch_db(db_path):
        from core.work_orders.artifacts import get_wo_artifact
        from core.work_orders.verify import attest_work_order

        out = attest_work_order(
            work_order_id=wo_id,
            reason="design-only work, verified by hand",
            source_root=repo,
            dream_studio_home=tmp_path,
            planning_root=tmp_path / "planning",
        )
        assert out["ok"], out
        stored = _json.loads(get_wo_artifact(wo_id, "review_verdict", db_path=db_path))

    assert stored["round_table"]["status"] == "not_convened"
    assert stored["round_table"]["seats"] == []
    assert "attestation" in stored["round_table"]["why"]


def test_the_review_skill_dispatches_the_subagent_through_the_table():
    """The operator's rule, made a property of the skill rather than of anyone's memory.

    A review is run by an agent that did not write the code, and that agent reviews
    through the registry -- not through a checklist it invents on the spot. The subagent
    section used to dispatch a "spec reviewer" and a "code quality reviewer" against a
    generic JSON schema with no mention of the table at all, while the table appeared
    only in a section addressed to the caller. So the bench existed and the dispatched
    reviewer never saw it.

    Asserted on the SUBAGENT SECTION specifically. The file mentions the table elsewhere,
    and checking the whole document would pass on exactly the arrangement that was wrong.
    """
    text = (REPO_ROOT / "canonical/skills/core/modes/review/SKILL.md").read_text(encoding="utf-8")
    start = text.index("## Subagent review")
    end = text.index("## Findings format", start)
    section = text[start:end]

    assert "core.gates.round_table" in section, (
        "the subagent dispatch does not name the round table, so a dispatched reviewer "
        "has no instruction to convene it"
    )
    assert "ASKED OF YOU" in section, "the judgment lanes must be put to the subagent"
    assert "not examined" in section, (
        "a lane the reviewer did not examine must be reportable as such -- without it, "
        "unexamined and clean are the same report"
    )
    assert "SELF-REVIEW" in section, "the circularity exception belongs in the dispatch"


def test_the_shipped_skill_carries_the_same_dispatch_rule():
    """A rule that lives only in canonical/ does not reach an installed adapter.

    `dist/plugin` is the shipped projection and is tracked, so it goes stale the moment
    canonical is edited without a rebuild -- which has happened four times in this repo
    and is registered as WO e3b4713c. This is that defect's tripwire for this file.
    """
    shipped = REPO_ROOT / "dist/plugin/skills/ds-core/modes/review/SKILL.md"
    if not shipped.is_file():
        pytest.skip("dist/plugin not built in this checkout")

    section = shipped.read_text(encoding="utf-8")
    assert "core.gates.round_table" in section
    assert "ASKED OF YOU" in section, (
        "dist/plugin is stale: canonical instructs the subagent to convene the table and "
        "the shipped copy does not. Rebuild with integrations.marketplace.plugin_dist"
    )


def test_no_lane_asks_more_than_its_enforcement_answers():
    """A detector's question must not be wider than the detector, silently.

    `a-branch-behind-its-base` asks "how far behind its base is this branch, AND did
    anyone ask it to sync". Its detector counts commits. The second half was answered by
    nobody while the lane rendered `clean` -- reporting clean on ground the check never
    examined, which is the signature several seats at this table exist to refuse, found on
    the table itself.

    The remedy is a DECLARATION, not a text heuristic. Measured first: a rule flagging
    compound questions would have flagged 21 of 30 lanes, because a setup sentence
    followed by a question is the house framing style here -- signal that fires on 70% of
    the population is noise. So each detector states what it does not decide, `defers: []`
    is the positive claim that it decides everything, and an absent key is refused.
    """
    lanes = yaml.safe_load(
        (REPO_ROOT / "canonical" / "review_lanes.yml").read_text(encoding="utf-8")
    )["lanes"]
    detectors = [ln for ln in lanes if "detector" in ln]
    assert detectors, "no detector lanes found -- the fixture is wrong, not the registry"

    for lane in detectors:
        assert "defers" in lane, (
            f"{lane['id']} runs a mechanical check and does not say what it leaves " "undecided"
        )
        assert isinstance(lane["defers"], list)

    # The lane the defect was found on, held by name so a future edit cannot quietly drop
    # the half that started this.
    steward = next(ln for ln in lanes if ln["id"] == "a-branch-behind-its-base")
    assert any("sync" in d for d in steward["defers"]), (
        "the steward asks whether anyone asked this branch to sync and its detector "
        "counts commits; that half must stay declared"
    )


def test_the_deferred_half_is_printed_beside_the_clean_mark():
    """A declaration nobody renders is a comment.

    The whole point is that a reviewer reading a `clean` detector lane is told, right
    there, what that clean mark does not cover -- so it is printed even when the lane is
    clean, which is the only case where the omission would mislead.
    """
    report = convene(run_detectors=False, all_seats=True)
    rendered = round_table._render(report)

    assert "NOT DECIDED HERE:" in rendered
    assert "did anyone ask it to sync" in rendered or "ASKED this branch to sync" in rendered

    steward = next(ln for ln in report["lanes"] if ln["lane"] == "a-branch-behind-its-base")
    assert steward["defers"], "the report must carry the declaration, not just the file"
