"""The pre-push gate: a branch's work order is not pushed while its lane review holds it.

Round three, receiver's view: the pushed-status gate governs a status, and this repository
pushes with plain `git push`, so nothing stood between an unreviewed branch and GitHub.
The gate runs where every push already stops, and keeps "not gated" apart from "clear".
"""

from __future__ import annotations

import sqlite3

import pytest
import yaml

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders.review_answers import record_answers, record_dispatch
from interfaces.cli.lane_review_gate import REPO_ROOT, evaluate

#: Credentials issued by each dispatch in this module, so recording helpers can present
#: the one issued to the reviewer they record for -- as a real reviewer must.
_ISSUED: dict = {}


def _issuing(fn):
    def wrapper(*args, **kwargs):
        doc = fn(*args, **kwargs)
        _ISSUED.update(doc.get("credentials") or {})
        return doc

    return wrapper


record_dispatch = _issuing(record_dispatch)

WO_ID = "abcdef12-0000-0000-0000-000000000000"
BRANCH = "feat/wo-abcdef12-the-thing"
REVIEWER = "review-gate-and-test-integrity"


def _faithful(image, repro):
    return True, {"exit_code": repro["exit_code"], "output_sha256": "x", "output_tail": ""}, "ok"


@pytest.fixture
def db(tmp_path):
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)
    now = "2026-09-23T00:00:00+00:00"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects (project_id, name, description, status, created_at,"
        " updated_at) VALUES ('p','P','','active',?,?)",
        (now, now),
    )
    conn.execute(
        "INSERT INTO business_work_orders (work_order_id, project_id, milestone_id, title,"
        " description, work_order_type, status, created_at, updated_at)"
        " VALUES (?, 'p', NULL, 'W', 'd', 'cleanup', 'in_review', ?, ?)",
        (WO_ID, now, now),
    )
    conn.commit()
    conn.close()
    return db


def _review(db, answers):
    record_dispatch(
        WO_ID,
        sha="d" * 40,
        image="ds-review:fake",
        change_set=[],
        db_path=db,
        assignments=[{"reviewer": REVIEWER, "seat": "s", "lanes": ["lane-one"]}],
        ownership={REVIEWER: {"lane-one"}},
    )
    record_answers(
        WO_ID,
        REVIEWER,
        answers,
        db_path=db,
        available=lambda: (True, ""),
        verify=_faithful,
        credential=_ISSUED.get(REVIEWER),
    )


def test_a_branch_whose_work_order_was_never_reviewed_cannot_push(db):
    code, message = evaluate(BRANCH, db)
    assert code == 1 and "BLOCKED" in message and "no review has been dispatched" in message


def test_an_open_finding_blocks_the_push(db):
    _review(
        db,
        [
            {
                "lane": "lane-one",
                "verdict": "finding",
                "evidence": "e",
                "reproduction": {"command": "false", "exit_code": 1},
            }
        ],
    )
    code, message = evaluate(BRANCH, db)
    assert code == 1 and "1 open finding(s)" in message


def test_a_cleared_review_lets_the_push_through(db):
    _review(
        db,
        [
            {
                "lane": "lane-one",
                "verdict": "pass",
                "reproduction": {"command": "true", "exit_code": 0},
            }
        ],
    )
    code, message = evaluate(BRANCH, db)
    assert code == 0 and message.startswith("lane-review: clear")


@pytest.mark.parametrize("branch", ["docs/typo-fix", None])
def test_a_branch_naming_no_work_order_is_not_gated_and_says_so(db, branch):
    """ "Not gated" is not "reviewed clean", and the output keeps them apart."""
    code, message = evaluate(branch, db)
    assert code == 0 and "NOT GATED" in message and "clear" not in message


def test_no_authority_is_not_gated_rather_than_passed():
    code, message = evaluate(BRANCH, None)
    assert code == 0 and "NOT GATED" in message


def test_the_pre_push_manifest_runs_it_as_blocking():
    manifest = yaml.safe_load(
        (REPO_ROOT / "canonical/workflows/pre-push.yaml").read_text(encoding="utf-8")
    )
    [gate] = [g for g in manifest["gates"] if g["id"] == "lane-review"]
    assert gate["tier"] == "blocking"
    assert gate["command"][-1] == "interfaces.cli.lane_review_gate"
