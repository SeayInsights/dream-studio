"""A task nobody can check cannot be filed, whichever door files it.

This is the third layer of one rule. `test_work_order_prompt_required.py` and
`test_milestone_prompt_required.py` cover the two above it: a milestone is the
prompt its work orders answer to, a work order is the prompt its tasks answer
to, and a task's acceptance criterion is how its prompt says it is done.

THE DEFECT WAS NOT THE MISSING CHECK -- the check existed. `admit_task` has
refused a criterion-less task since #706, and it is wired into the CLI's
`add-task` and into both of `verify_gaps`' spawners. It was never wired into
`create_task`, which is the door `core/work_orders/mutations.py` tells skills,
workflows and hooks to import directly.

Measured on the authority (2026-09-21, backup of the live studio.db): 1,850 of
3,679 tasks carry no acceptance criterion, and 330 of the 760 tasks created in
the month AFTER the CLI door was guarded -- 43% -- still arrived with none.
Only 53 tasks in the whole corpus used the declared-reason escape. A guard on
one of two writers holds for whichever writer the author happened to use.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.work_orders.admission import DECLARED_PREFIX, criterion_refusal, declared_reason
from core.work_orders.mutations import create_task

RUNNABLE = "TEST-CHECK: tests/unit/test_task_criterion_floor.py"
GOOD_WHY = "This is a documentation change; there is nothing to compute about prose."


def _create(**kw):
    """The floor runs before any database access, so no fixture is needed: a
    refusal returns before `_require_db` is reached."""
    kw.setdefault("title", "A task")
    return create_task(
        work_order_id="wo-1",
        project_id="p-1",
        source_root=Path("."),
        **kw,
    )


# --------------------------------------------------------------------------
# The floor itself
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "criteria,why,what",
    [
        (None, None, "nothing at all -- the 1,850-task case"),
        ("", None, "an empty criterion"),
        ("   \n ", None, "whitespace"),
        ("The button should look right.", None, "prose, which nothing executes"),
        ("TEST-CHECK: cargo", None, "a TEST-CHECK naming something unrunnable"),
        ("TEST-CHECK:", None, "a bare token with nothing after it"),
        (None, "too short", "a declared reason under the 20-character floor"),
        (None, "   ", "a whitespace reason"),
    ],
)
def test_a_task_nobody_can_check_is_refused(criteria, why, what):
    result = _create(acceptance_criteria=criteria, why=why)
    assert result["ok"] is False, what
    assert result["refusals"], "a refusal must say which lane refused"
    assert "remedy" in result


def test_a_runnable_criterion_passes_the_floor():
    """It must get PAST the floor. What happens after is not this test's business:
    run alone there is no authority and `_require_db` raises, while under the full
    suite conftest has stood one up."""
    try:
        result = _create(acceptance_criteria=RUNNABLE)
    except RuntimeError:
        return  # reached the database layer, which is the point
    if result.get("ok") is False:
        assert "cannot be filed" not in result["error"]


def test_a_declared_reason_passes_the_floor():
    try:
        result = _create(why=GOOD_WHY)
    except RuntimeError:
        return
    if result.get("ok") is False:
        assert "cannot be filed" not in result["error"]


# --------------------------------------------------------------------------
# The declaration is persisted, not spent
# --------------------------------------------------------------------------


def test_a_declared_reason_is_folded_into_the_description():
    """WO 82f608ca's rule, now applied at the door every author reaches. A reason
    that admits a task and then reaches only stdout is a bare bypass with a nicer
    spelling, and the criteria ratchet counts a task as declared only when the
    marker is on the row."""
    composed = __import__(
        "core.work_orders.admission", fromlist=["compose_declared_reason"]
    ).compose_declared_reason("Write the migration note.", GOOD_WHY)
    assert DECLARED_PREFIX in composed
    assert declared_reason(composed) == GOOD_WHY


def test_a_row_already_declared_stays_admitted_when_re_read():
    """A task filed on a declared reason is re-admissible from its own row. Without
    `declared_reason` the reason existed only in the `--why` passed once at the CLI,
    so re-filing the same row -- a carry-over, a replay -- would refuse it."""
    description = __import__(
        "core.work_orders.admission", fromlist=["compose_declared_reason"]
    ).compose_declared_reason("Body.", GOOD_WHY)
    assert criterion_refusal(None, description=description) is None


def test_a_description_with_no_marker_declares_nothing():
    assert declared_reason("Just a description.") == ""
    assert declared_reason(None) == ""
    assert criterion_refusal(None, description="Just a description.") is not None


# --------------------------------------------------------------------------
# The one exemption, and that it is narrow
# --------------------------------------------------------------------------


def test_a_carried_task_is_exempt_because_it_already_exists():
    """`carry_over` re-files an EXISTING task under a new work order. Refusing it
    would not raise the floor -- it would delete a task already in the authority
    because somebody else failed to write it a criterion years ago."""
    try:
        result = _create(acceptance_criteria=None, carried_from="task-abc")
    except RuntimeError:
        return  # past the floor, into the database layer
    if result.get("ok") is False:
        assert "cannot be filed" not in result["error"]


def test_the_exemption_needs_a_task_to_carry_from():
    """Narrow by construction: the exemption is a task id, not a boolean flag, so
    it cannot be set to "true" by an author who simply wants past the floor."""
    result = _create(acceptance_criteria=None, carried_from=None)
    assert result["ok"] is False


# --------------------------------------------------------------------------
# One predicate, not two opinions
# --------------------------------------------------------------------------


def test_the_floor_and_the_round_table_share_one_predicate():
    """`admit_task`'s Warden lane and the mutation's floor must agree by
    construction, not by both happening to be right today. That is the defect
    this milestone already paid for twice (WO eac7f657, 2 of 6 criteria
    disagreeing in BOTH directions)."""
    import inspect

    from core.work_orders import admission

    source = inspect.getsource(admission.criterion_refusal)
    assert "_warden(" in source, "the floor must call the Warden, not restate it"


def test_the_cli_hands_its_reason_to_the_mutation():
    """The CLI used to compose the declaration itself and the mutation did not, so
    a skill importing the mutation got neither the floor nor the marker. One
    composer, called from the door every author reaches."""
    source = Path("interfaces/cli/commands/work_order_query.py").read_text(encoding="utf-8")
    assert "why=why," in source, "the CLI must pass its reason down to create_task"
