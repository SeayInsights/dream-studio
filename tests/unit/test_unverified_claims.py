"""An asserted absence must cite the look that established it.

Operator ruling 2026-08-28: "those gates need to be adjusted so that you have to look
without assuming."

EVERY FIXTURE HERE IS REAL. Each string was written by me into the authority or into a
report during the session that produced this gate. Inventing them would repeat the mistake
that let the unreviewable-gap filter ship broken: the real stored value was
``rule = "N/A: independent review unverifiable - no diff provided"`` and the test asserted
against ``"N/A"``, a simplification I made up.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.gates.unverified_claims import audit_claims

NOW = "2026-08-28T00:00:00+00:00"


# Verbatim from a work order registered this session. The projection framework already
# dead-lettered after max retries and the live engine demonstrated it WHILE this was being
# written; the task had to be retitled "NO WORK NEEDED".
_FALSE_REGISTRATION = (
    "A projection that cannot apply an event because its referent does not exist must "
    "quarantine it after N attempts, not retry forever."
)

# The same claim, checked first. This is what should have been written.
_CHECKED_REGISTRATION = (
    "core/projections/framework.py already dead-letters after max_retries and continues.\n"
    "  Measured: SELECT COUNT(*) FROM projection_dead_letter -> 83 rows"
)


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "state" / "studio.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(path)
    return path


def _project_and_milestone(db: Path) -> tuple[str, str]:
    pid, mid = str(uuid.uuid4()), str(uuid.uuid4())
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (pid, "P", "", "active", NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_milestones"
        " (milestone_id, project_id, title, description, status, order_index,"
        "  created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (mid, pid, "M", "", "active", 1, NOW, NOW),
    )
    conn.commit()
    conn.close()
    return pid, mid


# -- The detector ---------------------------------------------------------------


def test_an_asserted_absence_with_no_citation_is_flagged():
    """The posture this catches is CONFIDENCE about the existing system without a look.
    It is more dangerous than a hedge: confident and wrong reads as fact, so nothing
    downstream questions it."""
    report = audit_claims(_FALSE_REGISTRATION)

    assert not report.passed
    assert len(report.unverified) == 1
    assert "does not exist" in report.unverified[0].trigger.lower()


def test_the_same_claim_with_its_evidence_passes():
    """A gate that flags a checked claim teaches authors to strip citations. The evidence
    is what distinguishes the two, and it must be sufficient."""
    assert audit_claims(_CHECKED_REGISTRATION).passed


def test_real_unchecked_claims_from_this_session_are_caught():
    """Driven against the actual sentences, not paraphrases."""
    for text in (
        "No gate covers the gitignore trap.",
        "This mechanism has no caller and is not wired to anything.",
        "There is no MCP server in Dream Studio.",
    ):
        assert not audit_claims(text).passed, f"slipped through: {text!r}"


def test_a_correction_is_not_a_new_claim():
    """Recording that a previous claim was false necessarily repeats it. Flagging the
    correction would penalise exactly the behaviour this gate wants."""
    corrected = (
        "CORRECTED: I registered this claiming an unprojectable event retries forever. "
        "That is false; the framework dead-letters after max retries."
    )
    assert audit_claims(corrected).passed


def test_a_rule_is_not_a_claim():
    """ "X must not happen" states intent. "X does not happen" states fact. Only the second
    is a claim about the system, and the hedge list is narrow on purpose -- a gate that
    flags every rule in a skill file would be bypassed within a day."""
    for rule in (
        "Never force-close a work order without operator approval.",
        "Product source edits must not happen without an active work order.",
        "Do not paraphrase a grader verdict.",
    ):
        assert audit_claims(rule).passed, f"a rule was read as a claim: {rule!r}"


def test_evidence_on_the_following_line_counts():
    """Evidence is normally pasted UNDER the sentence it supports -- the same window the
    evidence-backed-output gate uses."""
    text = "Nothing reads this key today.\n  grep -rn 'attachment_pressure' core/ -> 0 hits"
    assert audit_claims(text).passed


def test_the_report_says_what_would_settle_it():
    """ "Unverified claim at line 3" is half an answer. An author needs to know the fix is
    to run the check and paste the output."""
    rendered = audit_claims(_FALSE_REGISTRATION).render()
    assert "Run the check and paste what it said" in rendered
    assert "reads as fact" in rendered


# -- Wired where claims enter the authority -------------------------------------


def test_registering_a_work_order_stamps_its_unverified_claims(db, tmp_path):
    """Stamped at the moment the claim ENTERS the authority, because that is when it is
    cheapest to settle -- not discovered later by a reader who cannot tell a checked claim
    from an unchecked one."""
    from core.work_orders.mutations import create_work_order

    pid, mid = _project_and_milestone(db)
    result = create_work_order(
        project_id=pid,
        milestone_id=mid,
        title="T",
        description=_FALSE_REGISTRATION,
        work_order_type="infrastructure",
        source_root=tmp_path,
        dream_studio_home=tmp_path,
    )

    assert result["ok"] is True, "an unchecked claim must NOT block registration"
    assert result.get("unverified_claims"), "the unchecked claim must be surfaced"
    assert "does not exist" in result["unverified_claims"]


def test_a_checked_registration_carries_no_note(db, tmp_path):
    from core.work_orders.mutations import create_work_order

    pid, mid = _project_and_milestone(db)
    result = create_work_order(
        project_id=pid,
        milestone_id=mid,
        title="T",
        description=_CHECKED_REGISTRATION,
        work_order_type="infrastructure",
        source_root=tmp_path,
        dream_studio_home=tmp_path,
    )
    assert result["ok"] is True
    assert "unverified_claims" not in result


def test_registration_is_never_blocked_by_an_unchecked_claim(db, tmp_path):
    """A defect must ALWAYS be registerable. Refusing a registration would trade a small
    error - an unchecked claim - for a large one: an unrecorded defect."""
    from core.work_orders.mutations import create_work_order

    pid, mid = _project_and_milestone(db)
    result = create_work_order(
        project_id=pid,
        milestone_id=mid,
        title="T",
        description="Nothing checks this. No gate covers it. It has no caller.",
        work_order_type="infrastructure",
        source_root=tmp_path,
        dream_studio_home=tmp_path,
    )
    assert result["ok"] is True
    assert result["work_order_id"], "the work order exists despite the unchecked claims"


def test_a_task_description_is_audited_too(db, tmp_path):
    """Tasks carry claims as often as work orders do -- and a task is what an executor
    actually reads."""
    from core.work_orders.mutations import create_task, create_work_order

    pid, mid = _project_and_milestone(db)
    wo = create_work_order(
        project_id=pid,
        milestone_id=mid,
        title="T",
        description="See the measurement in the linked report.",
        work_order_type="infrastructure",
        source_root=tmp_path,
        dream_studio_home=tmp_path,
    )["work_order_id"]

    result = create_task(
        work_order_id=wo,
        project_id=pid,
        title="T1",
        description="There is no reader for this value anywhere in the codebase.",
        source_root=tmp_path,
        dream_studio_home=tmp_path,
    )
    assert result["ok"] is True
    assert result.get("unverified_claims"), "a task's claims must be audited too"


def test_a_quoted_claim_is_reported_not_asserted():
    """FOUND BY RUNNING THIS GATE ON THE PULL REQUEST THAT INTRODUCES IT.

    A "Claim | Reality" table quoting my own false statements was flagged as making them.
    Quoting a claim in order to correct it is the behaviour this gate wants; penalising it
    would teach authors to stop recording what they got wrong.

    Same accepted hole as the evidence gate's quotation exemption: an author can wrap an
    assertion in quotes to slip it past. A quoted claim reads as attribution, and flagging
    every correction table is the worse trade.
    """
    table_row = '| *"a projection ... retries forever"* | the framework already dead-lettered |'
    assert audit_claims(table_row).passed

    inline = 'The work order said "no gate covers this" and two gates partly did.'
    assert audit_claims(inline).passed


def test_an_unquoted_claim_on_the_same_line_is_still_caught():
    """The exemption must be narrow: a quotation elsewhere on the line must not launder an
    assertion made in the author's own voice."""
    mixed = 'He said "hello" and nothing checks this today.'
    assert not audit_claims(mixed).passed
