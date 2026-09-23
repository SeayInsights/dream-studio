"""The bench records what its reviewers TESTED, and a finding holds the work order.

WHY THIS FILE EXISTS. `convene()` asked the outstanding lanes and named a reviewer for
each; nothing carried an answer back. Then the operator's rule (2026-09-23): lanes use
Docker and run a real test, because that is the only thing that makes a lane better than
a hardcoded seat claiming something is wrong without testing it.

The first live convening of the reviewers against this surface returned twelve findings,
most reproduced by running code, and several are pinned here by name:
  - the record door recomputed scope, so a reviewer that answered exactly what it was
    dispatched was reported incomplete;
  - a later record silently replaced a finding with a pass;
  - a failed write (`stored=False`) still reported a complete review;
  - a mistyped work-order id recorded a "complete" review nothing would read;
  - 10 of 12 findings could not be filed as tasks, exited 0, and held nothing.

The sandbox is faked in most tests -- a container per test would make this file minutes
long -- and exercised against the real engine in `test_lane_sandbox.py`.
"""

from __future__ import annotations

import argparse
import json
import sqlite3

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.gates.round_table import assignments, convene
from core.work_orders import review_answers as ra
from core.work_orders.review_answers import (
    ARTIFACT_KIND,
    LANE_VERDICTS,
    file_findings_as_tasks,
    finding_as_task,
    open_findings,
    record_answers,
    record_dispatch,
    recorded_answers,
    review_status,
    validate_answers,
)

PROJECT_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
WO_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
NOW = "2026-09-23T00:00:00+00:00"
REVIEWER = "review-claim-integrity"
OTHER = "review-access-and-reach"
LANES = ["lane-one", "lane-two"]
IMAGE = "ds-review:fake"
FAILS = {"command": "python -m pytest /tmp/t.py -q", "exit_code": 1}
HOLDS = {"command": "python -m pytest tests/unit/test_x.py -q", "exit_code": 0}
REAL_TEST = "TEST-CHECK: tests/unit/test_review_answers.py::test_two_reviewers_answers_coexist"
#: The fake lanes' ownership, declared the way the registry declares the real ones.
OWNED = {
    REVIEWER: {"lane-one", "lane-two"},
    OTHER: {"lane-nine"},
    "seat:Chair and verdict owner": {"chair-lane"},
    "seat:Freshly Added Seat": {"new-lane"},
}


def _up():
    return True, "fake engine"


def _faithful(image, repro):
    """A sandbox in which every reproduction reproduces exactly as reported."""
    run = {"exit_code": repro["exit_code"], "output_sha256": "x", "output_tail": "ok"}
    return True, run, "reproduced"


def _record(db, reviewer, answers, **kw):
    kw.setdefault("available", _up)
    kw.setdefault("verify", _faithful)
    return record_answers(WO_ID, reviewer, answers, db_path=db, **kw)


def _dispatch(db, slots=None):
    slots = slots or [{"reviewer": REVIEWER, "seat": "Claim integrity", "lanes": LANES}]
    return record_dispatch(
        WO_ID,
        sha="a" * 40,
        image=IMAGE,
        change_set=["x.py"],
        assignments=slots,
        db_path=db,
        ownership=OWNED,
    )


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "state" / "studio.db"
    db_path.parent.mkdir(parents=True)
    bootstrap_database(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO business_projects (project_id, name, description, status,"
            " project_path, created_at, updated_at)"
            " VALUES (?, 'Test Project', 'desc', 'active', ?, ?, ?)",
            (PROJECT_ID, str(tmp_path), NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, NULL, 'WO-REVIEW-ANSWERS', 'desc', 'in_progress',"
            " 'infrastructure', ?, ?)",
            (WO_ID, PROJECT_ID, NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


# ── shape: the contract's own refusals ──────────────────────────────────────


def _shape(answers):
    return validate_answers(answers, reviewer=REVIEWER, assigned_lanes=LANES)


def test_a_reviewer_may_not_answer_a_lane_it_was_not_dispatched():
    accepted, refused = _shape([{"lane": "elsewhere", "verdict": "cannot-tell", "why": "x"}])
    assert accepted == []
    assert "was not dispatched this lane" in refused[0]["reason"]
    assert "lane-one" in refused[0]["reason"], "the refusal names what it DOES own"


@pytest.mark.parametrize("verdict", ["pass", "finding"])
def test_a_tested_verdict_without_a_reproduction_is_refused(verdict):
    """A LANE TESTS. A pass or finding from reading alone is the hardcoded-seat claim the
    lanes replaced; the only honest verdict without a run is cannot-tell."""
    _accepted, refused = _shape(
        [{"lane": "lane-one", "verdict": verdict, "evidence": "a.py:1", "why": "read it"}]
    )
    assert "must carry a reproduction" in refused[0]["reason"]
    assert "cannot-tell" in refused[0]["reason"]


def test_a_reproduction_must_report_an_integer_exit_code():
    _accepted, refused = _shape(
        [
            {
                "lane": "lane-one",
                "verdict": "pass",
                "reproduction": {"command": "true", "exit_code": True},
            }
        ]
    )
    assert "integer exit_code" in refused[0]["reason"]


def test_a_finding_with_no_evidence_is_refused():
    _accepted, refused = _shape([{"lane": "lane-one", "verdict": "finding", "reproduction": FAILS}])
    assert "opinion" in refused[0]["reason"]


def test_cannot_tell_needs_no_reproduction_and_is_kept_as_itself():
    accepted, refused = _shape(
        [{"lane": "lane-one", "verdict": "cannot-tell", "why": "would need the deploy logs"}]
    )
    assert refused == []
    assert accepted[0]["verdict"] == "cannot-tell"
    assert "cannot-tell" in LANE_VERDICTS


def test_cannot_tell_may_say_what_was_needed_in_evidence_as_the_contract_says():
    """The contract pointed reviewers at `evidence` for this and the code required `why`
    -- found by the claim-integrity seat. Either field now carries it."""
    accepted, refused = _shape(
        [{"lane": "lane-one", "verdict": "cannot-tell", "evidence": "needed the prod DB"}]
    )
    assert refused == [] and accepted


def test_cannot_tell_with_nothing_said_is_refused():
    _accepted, refused = _shape([{"lane": "lane-one", "verdict": "cannot-tell"}])
    assert "what would have been needed" in refused[0]["reason"]


def test_an_unknown_verdict_is_refused_naming_the_set():
    _accepted, refused = _shape([{"lane": "lane-one", "verdict": "lgtm"}])
    for verdict in LANE_VERDICTS:
        assert verdict in refused[0]["reason"]


def test_the_same_lane_answered_twice_is_refused_once():
    accepted, refused = _shape(
        [
            {"lane": "lane-one", "verdict": "finding", "evidence": "a", "reproduction": FAILS},
            {"lane": "lane-one", "verdict": "pass", "reproduction": HOLDS},
        ]
    )
    assert [a["verdict"] for a in accepted] == ["finding"]
    assert "answered twice" in refused[0]["reason"]


def test_declare_is_kept_so_the_route_the_contract_names_is_reachable():
    """The claim-integrity seat found `declare` read by finding_as_task and stripped by
    validation -- a route only a test could reach."""
    accepted, _ = _shape(
        [
            {
                "lane": "lane-one",
                "verdict": "finding",
                "evidence": "a.py:1",
                "reproduction": FAILS,
                "declare": "readability judgment; no query or test decides it",
            }
        ]
    )
    assert accepted[0]["declare"].startswith("readability")


# ── the submission-level refusals ───────────────────────────────────────────


def test_an_unknown_work_order_is_refused(db):
    result = record_answers("no-such-wo", REVIEWER, [], db_path=db, available=_up)
    assert "no work order" in result["refused_submission"]


def test_answers_before_any_dispatch_are_refused(db):
    result = _record(db, REVIEWER, [])
    assert "no dispatch is recorded" in result["refused_submission"]


def test_a_reviewer_dispatched_nothing_is_refused(db):
    _dispatch(db)
    assert "dispatched no lane" in _record(db, OTHER, [])["refused_submission"]


def test_docker_down_records_nothing(db):
    """No fallback to trust: a reproduction the door cannot run is not recorded."""
    _dispatch(db)
    result = _record(
        db,
        REVIEWER,
        [{"lane": "lane-one", "verdict": "pass", "reproduction": HOLDS}],
        available=lambda: (False, "engine not running"),
    )
    assert "cannot re-run reproductions" in result["refused_submission"]
    assert recorded_answers(WO_ID, db_path=db) == []


def test_a_reproduction_that_does_not_reproduce_is_refused(db):
    _dispatch(db)

    def liar_caught(image, repro):
        return False, {"exit_code": 0}, "re-run exited 0, the reviewer reported 1"

    result = _record(
        db,
        REVIEWER,
        [{"lane": "lane-one", "verdict": "finding", "evidence": "x", "reproduction": FAILS}],
        verify=liar_caught,
    )
    assert result["accepted"] == []
    assert "reviewer reported 1" in result["refused"][0]["reason"]
    assert open_findings(WO_ID, db_path=db) == []


def test_the_door_reruns_in_the_rounds_image(db):
    _dispatch(db)
    seen = []

    def spy(image, repro):
        seen.append((image, repro["command"]))
        return _faithful(image, repro)

    _record(
        db, REVIEWER, [{"lane": "lane-one", "verdict": "pass", "reproduction": HOLDS}], verify=spy
    )
    assert seen == [(IMAGE, HOLDS["command"])]


# ── recording ───────────────────────────────────────────────────────────────


def test_answering_exactly_what_was_dispatched_is_complete(db):
    """Three reviewers independently found the door recomputing scope over the whole
    bench, so a reviewer that answered its one dispatched lane got complete=false and
    exit 1. The record is held to the dispatch, not to a recomputation."""
    _dispatch(db, [{"reviewer": REVIEWER, "seat": "s", "lanes": ["lane-one"]}])
    result = _record(db, REVIEWER, [{"lane": "lane-one", "verdict": "pass", "reproduction": HOLDS}])
    assert result["unanswered"] == []
    assert result["complete"] is True


def test_a_partial_submission_reports_what_is_still_unanswered(db):
    _dispatch(db)
    result = _record(db, REVIEWER, [{"lane": "lane-one", "verdict": "pass", "reproduction": HOLDS}])
    assert result["unanswered"] == ["lane-two"]
    assert result["complete"] is False


def test_a_write_that_did_not_land_is_not_a_complete_review(db, monkeypatch):
    """`stored` was returned and read by nothing: against an older table layout the door
    exited 0, complete=True, having written 0 rows."""
    _dispatch(db, [{"reviewer": REVIEWER, "seat": "s", "lanes": ["lane-one"]}])
    import core.work_orders.artifacts as artifacts

    monkeypatch.setattr(artifacts, "set_wo_artifact", lambda *a, **k: False)
    result = _record(db, REVIEWER, [{"lane": "lane-one", "verdict": "pass", "reproduction": HOLDS}])
    assert result["stored"] is False
    assert result["complete"] is False


def test_a_later_pass_resolves_a_finding_visibly_rather_than_erasing_it(db):
    """A later record used to REPLACE the reviewer's document, so a finding simply
    vanished. Now every submission is kept and the pass names the round it resolved."""
    _dispatch(db)
    _record(
        db,
        REVIEWER,
        [{"lane": "lane-one", "verdict": "finding", "evidence": "a.py:1", "reproduction": FAILS}],
    )
    assert [f["lane"] for f in open_findings(WO_ID, db_path=db)] == ["lane-one"]

    _dispatch(db)  # round 2, after the fix
    _record(db, REVIEWER, [{"lane": "lane-one", "verdict": "pass", "reproduction": HOLDS}])

    assert open_findings(WO_ID, db_path=db) == []
    [answer] = [a for a in recorded_answers(WO_ID, db_path=db) if a["lane"] == "lane-one"]
    assert answer["verdict"] == "pass"
    assert answer["resolves_finding_from_round"] == 1
    doc = ra._reviewer_doc(WO_ID, REVIEWER, db_path=db)
    assert len(doc["submissions"]) == 2, "the finding's submission is history, not overwritten"


def test_recorded_answers_carry_their_verified_run(db):
    _dispatch(db)
    _record(
        db,
        REVIEWER,
        [{"lane": "lane-two", "verdict": "finding", "evidence": "x.py:42", "reproduction": FAILS}],
    )
    [finding] = open_findings(WO_ID, db_path=db)
    assert finding["run"]["exit_code"] == 1
    assert finding["run"]["image"] == IMAGE


def test_lane_answers_do_not_collide_with_the_verify_verdict(db):
    from core.work_orders.artifacts import get_wo_artifact, set_wo_artifact

    set_wo_artifact(WO_ID, ARTIFACT_KIND, json.dumps({"round_table": {"seats": []}}), db_path=db)
    _dispatch(db)
    _record(db, REVIEWER, [{"lane": "lane-one", "verdict": "pass", "reproduction": HOLDS}])
    assert [a["lane"] for a in recorded_answers(WO_ID, db_path=db)] == ["lane-one"]
    assert json.loads(get_wo_artifact(WO_ID, ARTIFACT_KIND, db_path=db))["round_table"] == {
        "seats": []
    }


def test_two_reviewers_answers_coexist(db):
    _dispatch(
        db,
        [
            {"reviewer": REVIEWER, "seat": "a", "lanes": ["lane-one"]},
            {"reviewer": OTHER, "seat": "b", "lanes": ["lane-nine"]},
        ],
    )
    _record(db, REVIEWER, [{"lane": "lane-one", "verdict": "pass", "reproduction": HOLDS}])
    _record(db, OTHER, [{"lane": "lane-nine", "verdict": "pass", "reproduction": HOLDS}])
    assert {a["reviewer"] for a in recorded_answers(WO_ID, db_path=db)} == {REVIEWER, OTHER}


# ── the dispatch ────────────────────────────────────────────────────────────


def test_each_dispatch_is_a_new_round(db):
    assert _dispatch(db)["round"] == 1
    assert _dispatch(db)["round"] == 2


def test_an_open_finding_is_carried_into_the_next_round_even_off_scope(db):
    """A fix that moves the change to other files must not escape re-review: the lane
    holding the finding is dispatched again whether or not the new diff selects it."""
    _dispatch(db)
    _record(
        db,
        REVIEWER,
        [{"lane": "lane-two", "verdict": "finding", "evidence": "x", "reproduction": FAILS}],
    )
    doc = _dispatch(db, [{"reviewer": OTHER, "seat": "b", "lanes": ["lane-nine"]}])
    assert "lane-two" in ra.dispatched_lanes(doc, REVIEWER)
    assert doc["carried_open_findings"] == ["lane-two"]


# ── the work order is held by the finding itself ────────────────────────────


def test_no_dispatch_blocks(db):
    status = review_status(WO_ID, db_path=db)
    assert status["blocking"] is True
    assert "no review has been dispatched" in status["reasons"][0]


def test_an_unanswered_lane_blocks(db):
    _dispatch(db)
    _record(db, REVIEWER, [{"lane": "lane-one", "verdict": "pass", "reproduction": HOLDS}])
    status = review_status(WO_ID, db_path=db)
    assert status["blocking"] is True
    assert status["unanswered"] == {REVIEWER: ["lane-two"]}


def test_an_unfilable_finding_blocks_exactly_as_hard_as_a_filed_one(db):
    """The mission finding: 10 of 12 findings could not be filed (no executable check yet),
    the command exited 0, and nothing held the work order. The finding holds it now,
    filed or not."""
    _dispatch(db)
    _record(
        db,
        REVIEWER,
        [
            {"lane": "lane-one", "verdict": "pass", "reproduction": HOLDS},
            {"lane": "lane-two", "verdict": "finding", "evidence": "x", "reproduction": FAILS},
        ],
    )
    filed = file_findings_as_tasks(WO_ID, project_id=PROJECT_ID, db_path=db)
    assert filed["added"] == 0 and filed["unfiled"]
    status = review_status(WO_ID, db_path=db)
    assert status["blocking"] is True
    assert "1 open finding(s)" in status["reasons"]


def test_a_fully_answered_clean_round_does_not_block(db):
    _dispatch(db)
    _record(
        db,
        REVIEWER,
        [
            {"lane": "lane-one", "verdict": "pass", "reproduction": HOLDS},
            {"lane": "lane-two", "verdict": "cannot-tell", "why": "needs prod traffic"},
        ],
    )
    status = review_status(WO_ID, db_path=db)
    assert status["blocking"] is False, status["reasons"]
    assert [c["lane"] for c in status["cannot_tell"]] == ["lane-two"], "reported, not hidden"


def test_the_chairs_lanes_are_reported_not_gated(db):
    _dispatch(
        db,
        [
            {"reviewer": REVIEWER, "seat": "a", "lanes": ["lane-one"]},
            {"reviewer": None, "seat": ra.CHAIR_SEAT, "lanes": ["chair-lane"]},
        ],
    )
    _record(db, REVIEWER, [{"lane": "lane-one", "verdict": "pass", "reproduction": HOLDS}])
    status = review_status(WO_ID, db_path=db)
    assert status["blocking"] is False
    assert status["chair_lanes"] == ["chair-lane"]


# ── findings become work ────────────────────────────────────────────────────


def test_a_finding_is_titled_by_its_lane_not_by_its_wording():
    one = finding_as_task({"lane": "a-test-that-cannot-fail", "why": "tautology"})
    two = finding_as_task({"lane": "a-test-that-cannot-fail", "why": "can never go red"})
    assert one["title"] == two["title"]


def test_a_finding_carries_its_evidence_and_reproduction_into_the_task():
    task = finding_as_task(
        {
            "lane": "l",
            "evidence": "tests/unit/test_x.py:12 asserts True",
            "why": "tautological",
            "reviewer": "review-gate-and-test-integrity",
            "reproduction": FAILS,
        }
    )
    assert "tests/unit/test_x.py:12" in task["description"]
    assert FAILS["command"] in task["description"], "whoever fixes it can run it"


def test_a_findings_prose_never_arrives_as_a_declared_reason():
    """Found by this file in round one: prose routed into admission's `why` opened the
    enforce-or-declare door on length alone. A declaration is deliberate or absent."""
    plain = finding_as_task({"lane": "l", "why": "a long explanation " * 10, "evidence": "e"})
    assert plain["why"] is None
    declared = finding_as_task(
        {"lane": "l", "why": "w", "evidence": "e", "declare": "no check can"}
    )
    assert declared["why"] == "no check can"


def test_a_finding_with_an_executable_check_is_filed_once(db):
    _dispatch(db)
    _record(
        db,
        REVIEWER,
        [
            {
                "lane": "lane-two",
                "verdict": "finding",
                "evidence": "x.py:42",
                "reproduction": FAILS,
                "check": REAL_TEST,
            }
        ],
    )
    first = file_findings_as_tasks(WO_ID, project_id=PROJECT_ID, db_path=db)
    second = file_findings_as_tasks(WO_ID, project_id=PROJECT_ID, db_path=db)
    assert first["added"] == 1, first["unfiled"]
    assert second["added"] == 0, "re-review must not accumulate duplicate tasks"
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            "SELECT title, acceptance_criteria FROM business_tasks WHERE work_order_id = ?",
            (WO_ID,),
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 1 and "TEST-CHECK" in rows[0][1]


# ── the dispatch grouping ───────────────────────────────────────────────────


def test_assignments_group_the_outstanding_lanes_by_reviewer():
    report = convene(run_detectors=False, all_seats=True)
    plan = assignments(report)
    assert len([a for a in plan if a["reviewer"]]) == 9
    assigned = [lane for slot in plan for lane in slot["lanes"]]
    assert sorted(assigned) == sorted(report["awaiting_judgment"])
    assert len(assigned) == len(set(assigned))


def test_the_chair_is_listed_with_no_reviewer_rather_than_dropped():
    plan = assignments(convene(run_detectors=False, all_seats=True))
    [chair] = [a for a in plan if a["reviewer"] is None]
    assert chair["seat"] == "Chair and verdict owner" and chair["lanes"]


def test_a_detector_lane_is_not_assigned_to_a_reviewer():
    report = convene(run_detectors=False, all_seats=True)
    detectors = {e["lane"] for e in report["lanes"] if e["kind"] == "detector"}
    assert detectors
    assert not detectors & {ln for s in assignments(report) for ln in s["lanes"]}


def test_assignments_follow_the_reports_own_outstanding_set():
    report = convene(run_detectors=False, all_seats=True)
    report["awaiting_judgment"] = report["awaiting_judgment"][:2]
    assigned = [ln for s in assignments(report) for ln in s["lanes"]]
    assert sorted(assigned) == sorted(report["awaiting_judgment"])


# ── the CLI doors ───────────────────────────────────────────────────────────


def _cli(argv, home, monkeypatch, *, engine=True):
    """Drive the REAL parser and dispatcher, with the sandbox faked."""
    from core.gates import lane_sandbox
    from interfaces.cli.commands import review

    monkeypatch.setattr(lane_sandbox, "docker_available", lambda: (engine, "fake"))
    monkeypatch.setattr(lane_sandbox, "verify_reproduction", _faithful)
    parser = argparse.ArgumentParser(prog="ds")
    sub = parser.add_subparsers(dest="command", required=True)
    review.register(sub)
    args = parser.parse_args(["review", *argv])
    from pathlib import Path

    return review.dispatch(args, source_root=Path.cwd(), dream_studio_home=home)


@pytest.fixture
def home(db):
    return db.parent.parent  # <home>/state/studio.db


def test_cli_record_exits_0_on_a_complete_review(db, home, tmp_path, monkeypatch):
    _dispatch(db)
    f = tmp_path / "a.json"
    f.write_text(
        json.dumps(
            [
                {"lane": "lane-one", "verdict": "pass", "reproduction": HOLDS},
                {"lane": "lane-two", "verdict": "cannot-tell", "why": "needs prod"},
            ]
        ),
        encoding="utf-8",
    )
    code = _cli(
        ["--record", str(f), "--reviewer", REVIEWER, "--work-order", WO_ID], home, monkeypatch
    )
    assert code == 0


def test_cli_record_exits_1_when_an_answer_is_refused(db, home, tmp_path, monkeypatch):
    _dispatch(db)
    f = tmp_path / "a.json"
    f.write_text(json.dumps([{"lane": "lane-one", "verdict": "pass"}]), encoding="utf-8")
    code = _cli(
        ["--record", str(f), "--reviewer", REVIEWER, "--work-order", WO_ID], home, monkeypatch
    )
    assert code == 1


def test_cli_record_with_a_missing_file_exits_2_not_a_traceback(home, monkeypatch, capsys):
    code = _cli(
        ["--record", "nope.json", "--reviewer", REVIEWER, "--work-order", WO_ID], home, monkeypatch
    )
    assert code == 2
    assert "cannot read" in capsys.readouterr().err


def test_cli_record_refuses_an_object_that_is_not_a_submission(db, home, tmp_path, monkeypatch):
    """It used to become an empty submission that overwrote the answer already recorded."""
    _dispatch(db)
    _record(db, REVIEWER, [{"lane": "lane-one", "verdict": "pass", "reproduction": HOLDS}])
    f = tmp_path / "a.json"
    f.write_text(json.dumps({"verdicts": []}), encoding="utf-8")
    code = _cli(
        ["--record", str(f), "--reviewer", REVIEWER, "--work-order", WO_ID], home, monkeypatch
    )
    assert code == 2
    assert [a["lane"] for a in recorded_answers(WO_ID, db_path=db)] == ["lane-one"]


def test_cli_record_with_docker_down_exits_2(db, home, tmp_path, monkeypatch):
    _dispatch(db)
    f = tmp_path / "a.json"
    f.write_text(
        json.dumps([{"lane": "lane-one", "verdict": "pass", "reproduction": HOLDS}]),
        encoding="utf-8",
    )
    code = _cli(
        ["--record", str(f), "--reviewer", REVIEWER, "--work-order", WO_ID],
        home,
        monkeypatch,
        engine=False,
    )
    assert code == 2


def test_cli_status_exits_1_while_the_review_blocks(db, home, monkeypatch):
    _dispatch(db)
    assert _cli(["--status", "--work-order", WO_ID], home, monkeypatch) == 1
    _record(
        db,
        REVIEWER,
        [
            {"lane": "lane-one", "verdict": "pass", "reproduction": HOLDS},
            {"lane": "lane-two", "verdict": "pass", "reproduction": HOLDS},
        ],
    )
    assert _cli(["--status", "--work-order", WO_ID], home, monkeypatch) == 0


def test_cli_as_tasks_exits_1_when_a_finding_is_unfiled(db, home, monkeypatch):
    _dispatch(db)
    _record(
        db,
        REVIEWER,
        [{"lane": "lane-one", "verdict": "finding", "evidence": "x", "reproduction": FAILS}],
    )
    assert _cli(["--findings", "--as-tasks", "--work-order", WO_ID], home, monkeypatch) == 1


@pytest.mark.parametrize(
    "argv",
    [
        ["--as-tasks"],
        ["--reviewer", REVIEWER],
        ["--status"],
        ["--run", "true"],
        ["--record", "a.json", "--work-order", WO_ID],
    ],
)
def test_cli_a_flag_without_its_companion_is_refused_not_ignored(argv, home, monkeypatch):
    assert _cli(argv, home, monkeypatch) == 2


def test_cli_dispatch_preview_returns_assignments_and_records_nothing(
    db, home, monkeypatch, capsys
):
    code = _cli(["--dispatch", "--all", "--no-detectors"], home, monkeypatch)
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert len([a for a in out["assignments"] if a["reviewer"]]) == 9
    assert out["recorded"] is False
    assert ra.read_dispatch(WO_ID, db_path=db) is None


# ── the dispatch door is held to the registry ───────────────────────────────


def test_a_dispatch_may_not_hand_a_reviewer_another_seats_lane(db):
    """Round two's access-and-reach finding, against the REAL registry: dispatching
    review-access-and-reach a Publication and provenance lane was accepted, and a verified
    pass on it recorded. Round one's widening had moved to this door, not closed."""
    with pytest.raises(ValueError, match="does not own supply-chain-and-provenance"):
        record_dispatch(
            WO_ID,
            sha="a" * 40,
            image=IMAGE,
            change_set=["x.py"],
            assignments=[
                {
                    "reviewer": "review-access-and-reach",
                    "seat": "Access and reach",
                    "lanes": ["authz-and-identity", "supply-chain-and-provenance"],
                }
            ],
            db_path=db,
        )
    assert ra.read_dispatch(WO_ID, db_path=db) is None, "a refused dispatch records nothing"


def test_the_registry_ownership_gives_every_lane_exactly_one_owner():
    from core.gates.round_table import _lanes

    owned = ra.lane_ownership()
    every = [lane for lanes in owned.values() for lane in lanes]
    assert sorted(every) == sorted(str(ln["id"]) for ln in _lanes())
    assert len(every) == len(set(every))
    assert (
        "reviewer-s-reviewer" in owned["review-finding-integrity"]
    ), "an abstaining seat still owns its lane in later rounds"


def test_a_seat_with_no_compiled_reviewer_keeps_its_own_seat_and_blocks():
    """Round two, boundary-semantics: every reviewer-less lane was filed under the chair,
    whose lanes are not gated -- so a seat added before its agent compiled would have been
    waved through. It keeps its own seat, and nobody being able to answer it blocks."""
    report = {
        "awaiting_judgment": ["new-lane", "chair-lane"],
        "lanes": [
            {"lane": "new-lane", "seat": "Freshly Added Seat", "reviewer": None},
            {"lane": "chair-lane", "seat": ra.CHAIR_SEAT, "reviewer": None},
        ],
    }
    slots = {s["seat"]: s for s in assignments(report)}
    assert slots["Freshly Added Seat"]["lanes"] == ["new-lane"]
    assert slots[ra.CHAIR_SEAT]["lanes"] == ["chair-lane"]


def test_a_reviewerless_seat_that_is_not_the_chair_blocks_the_work_order(db):
    _dispatch(db, [{"reviewer": None, "seat": "Freshly Added Seat", "lanes": ["new-lane"]}])
    status = review_status(WO_ID, db_path=db)
    assert status["blocking"] is True
    assert status["unanswered"] == {"(no reviewer compiled for Freshly Added Seat)": ["new-lane"]}


def test_a_dispatch_against_no_work_order_is_refused_by_the_mechanism(db):
    """Round two, boundary-semantics: only the CLI handler checked, so any other caller
    could record a round against an id that names nothing."""
    with pytest.raises(ValueError, match="no work order"):
        record_dispatch(
            "no-such-wo",
            sha="a" * 40,
            image=IMAGE,
            change_set=["x.py"],
            assignments=[{"reviewer": REVIEWER, "seat": "s", "lanes": ["lane-one"]}],
            db_path=db,
            ownership=OWNED,
        )


# ── a finding resolves only when its own test goes green ────────────────────


def _world(exit_codes):
    """A sandbox where each command has one true exit code, as in a real image.

    `_faithful` echoes whatever is claimed, which would let any resolution through; this
    models the thing the door exists to check.
    """

    def verify(image, repro):
        actual = exit_codes.get(repro["command"], 0)
        run = {"exit_code": actual, "output_sha256": "x", "output_tail": ""}
        if actual != repro["exit_code"]:
            return False, run, f"re-run exited {actual}, the reviewer reported {repro['exit_code']}"
        return True, run, "reproduced"

    return verify


def _open_a_finding(db):
    _dispatch(db)
    _record(
        db,
        REVIEWER,
        [{"lane": "lane-one", "verdict": "finding", "evidence": "x.py:1", "reproduction": FAILS}],
        verify=_world({FAILS["command"]: 1}),
    )
    assert [f["lane"] for f in open_findings(WO_ID, db_path=db)] == ["lane-one"]


def test_a_vacuous_pass_does_not_resolve_a_finding_whose_test_still_fails(db):
    """Round three, access-and-reach: `true`, exit 0, under the reviewer's name closed a real
    open finding. The pass's own command held; the defect was untouched."""
    _open_a_finding(db)
    _dispatch(db)
    result = _record(
        db,
        REVIEWER,
        [
            {
                "lane": "lane-one",
                "verdict": "pass",
                "reproduction": {"command": "true", "exit_code": 0},
            }
        ],
        verify=_world({FAILS["command"]: 1, "true": 0}),
    )
    assert result["accepted"] == []
    assert "own reproduction now exits 0" in result["refused"][0]["reason"]
    assert [f["lane"] for f in open_findings(WO_ID, db_path=db)] == ["lane-one"]


def test_a_pass_resolves_a_finding_when_the_findings_test_now_passes(db):
    _open_a_finding(db)
    _dispatch(db)
    result = _record(
        db,
        REVIEWER,
        [{"lane": "lane-one", "verdict": "pass", "reproduction": HOLDS}],
        verify=_world({FAILS["command"]: 0, HOLDS["command"]: 0}),  # the fix landed
    )
    assert result["refused"] == [], result["refused"]
    assert open_findings(WO_ID, db_path=db) == []
    [answer] = [a for a in recorded_answers(WO_ID, db_path=db) if a["lane"] == "lane-one"]
    assert answer["resolution_run"]["command"] == FAILS["command"]


def test_a_later_cannot_tell_does_not_clear_a_finding(db):
    """Found probing round three's sibling: "I could not tell" displaced the finding and the
    work order unblocked. It is recorded against the lane, and the finding stays open."""
    _open_a_finding(db)
    _dispatch(db)
    _record(db, REVIEWER, [{"lane": "lane-one", "verdict": "cannot-tell", "why": "could not see"}])
    [still] = open_findings(WO_ID, db_path=db)
    assert still["lane"] == "lane-one" and still["cannot_tell_rounds"] == [2]
    status = review_status(WO_ID, db_path=db)
    assert status["blocking"] is True
    assert (
        REVIEWER not in status["unanswered"] or "lane-one" not in status["unanswered"][REVIEWER]
    ), "the cannot-tell still answers the lane this round"


def test_two_reviewerless_seats_do_not_share_ownership(db, monkeypatch):
    """Round three, boundary-semantics: ownership keyed by reviewer put every reviewer-less
    seat in one None bucket, so a new seat's lane could be dispatched under the chair.

    Ownership is DERIVED here, from a registry holding two seats with no compiled
    reviewer, because an injected mapping already keyed per seat cannot see the collapse:
    the first version of this test did exactly that and passed with the bug restored.
    """
    import core.gates.round_table as rt

    monkeypatch.setattr(
        rt,
        "_lanes",
        lambda repo_root=None: [
            {"id": "chair-lane", "seat": ra.CHAIR_SEAT},
            {"id": "new-lane", "seat": "Freshly Added Seat"},
        ],
    )

    def dispatch(seat, lane):
        return record_dispatch(
            WO_ID,
            sha="a" * 40,
            image=IMAGE,
            change_set=["x.py"],
            assignments=[{"reviewer": None, "seat": seat, "lanes": [lane]}],
            db_path=db,
        )

    with pytest.raises(ValueError, match="does not own new-lane"):
        dispatch(ra.CHAIR_SEAT, "new-lane")
    # And the right pairing is accepted, so the refusal above is about the seat, not a
    # guard that refuses every reviewer-less lane.
    assert dispatch("Freshly Added Seat", "new-lane")["stored"]


def test_the_registry_keys_the_chair_by_its_seat():
    owned = ra.lane_ownership()
    assert "chair-and-verdict-owner" in owned[f"seat:{ra.CHAIR_SEAT}"]
    assert None not in owned
