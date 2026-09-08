"""`--skip-verify` must waive an UNREVIEWABLE verdict, and must never waive a failed one.

THE DEFECT, measured 2026-09-08. The flag guarded only the DEFAULT-ON review branch, so for
every work order type whose declared ``post_gate`` IS ``independent_review`` -- infrastructure
among them -- it was inert. Four work orders whose graders had all returned "You've hit your
session limit - resets 5pm" refused ``--skip-verify`` and closed only under ``--force``, which
bypasses every gate at once instead of the one that could not run.

The flag's help text says it skips the independent review for this close. It did not do that
for the population an operator reaches for it with, which is the unachievable-remedy shape
this repo keeps finding: a prescribed command that does not work drives the operator to the
louder instrument, and ``--force`` waives ``tasks_done`` and ``change_impact_affirmed`` too.

THE LINE THAT MATTERS. An UNREVIEWABLE verdict is not a judgment -- it is the provider
reporting it could not produce one -- so skipping it withholds certification without
asserting the work is sound. A verdict that FAILED on substance is a finding about the work,
and waiving that would be the false-done the gate exists to prevent. Only ``--force`` passes
it, and that is a louder, separately recorded act. Both directions are asserted, because a
fix that waived both would look identical on the four work orders that motivated it.
"""

from __future__ import annotations

import pytest

from core.work_orders import close_main

_UNREVIEWABLE = (
    "independent_review: unreviewable — independent review unreviewable: grader(s)"
    " [completion, quality] did not produce a verdict — completion: Grader returned"
    " non-JSON.\nRaw:\nYou've hit your session limit · resets 5pm (America/New_York)"
)
_REVIEW_FAILED = (
    "independent_review: review failed [quality 0.62, correctness 0.79] — task 1 ships"
    " untested and its acceptance criterion names a pre-existing test."
)
_OTHER_GATE = "tasks_done: 3 task(s) not marked done"


def _waive(failures: list[str], *, skip_verify: bool) -> tuple[list[str], list[str]]:
    """Call the REAL waiver the close applies.

    The first version of this helper reimplemented the predicate, while its docstring
    claimed it drove the real one. That is the defect being corrected in the same session
    the lesson was written -- a test of its own copy proves nothing about the branch that
    ships, and it would have passed against a close whose waiver was still missing from the
    post-gate path. The predicate now lives in ``waive_unreviewable_review`` precisely so
    both the close and this test can call it.
    """
    return close_main.waive_unreviewable_review(
        list(failures), work_order_id="wo-skip-0001", skip_verify=skip_verify
    )


def test_the_close_waives_on_the_post_gate_path_not_only_the_default_on_one():
    """The waiver runs against the failures _evaluate_gates produces.

    This assertion previously looked for the inline predicate, and extracting that
    predicate into ``waive_unreviewable_review`` made it stale -- an instance of the rule
    that a diff bounds where you hunt but not what it invalidates. It now checks the
    call and its ORDER, which is what actually has to hold: placed before
    ``_evaluate_gates`` the waiver would filter a list that does not yet contain the
    post-gate failure, and --skip-verify would be inert again for every type whose
    post_gate is independent_review.
    """
    import inspect

    source = inspect.getsource(close_main.close_work_order)
    marker = "waive_unreviewable_review("
    assert marker in source, "close_work_order no longer applies the waiver at all"
    assert source.index("_evaluate_gates(") < source.index(marker), (
        "the waiver runs before the gates it filters, so the post-gate failure is not yet"
        " in the list"
    )


def test_an_unreviewable_verdict_is_waived_and_returned_for_recording():
    remaining, waived = _waive([_UNREVIEWABLE], skip_verify=True)
    assert remaining == []
    assert len(waived) == 1, "a waiver that returns nothing leaves no bypass to record"
    assert "session limit" in waived[0]


def test_the_close_records_every_waived_reason():
    """The waiver returns them; the close must WRITE them. A bypass with no record is the
    silent-escape shape, and the flag's help promises "never silent"."""
    import inspect

    source = inspect.getsource(close_main.close_work_order)
    assert "record_gate_bypass(" in source
    assert (
        "for _reason in _waived:" in source
    ), "each waived reason must be recorded, not just the first"


def test_a_failed_review_is_never_waived():
    """The false-done guard. --force remains the only way past a substantive failure."""
    remaining, waived = _waive([_REVIEW_FAILED], skip_verify=True)
    assert remaining == [_REVIEW_FAILED]
    assert waived == []


def test_a_mixed_result_waives_only_the_unreviewable_one():
    remaining, _ = _waive([_UNREVIEWABLE, _REVIEW_FAILED], skip_verify=True)
    assert remaining == [_REVIEW_FAILED]


def test_other_gates_are_untouched():
    """--skip-verify names the review. It is not a general bypass; --force is."""
    remaining, _ = _waive([_UNREVIEWABLE, _OTHER_GATE], skip_verify=True)
    assert remaining == [_OTHER_GATE]


def test_without_the_flag_nothing_is_waived():
    remaining, waived = _waive([_UNREVIEWABLE], skip_verify=False)
    assert remaining == [_UNREVIEWABLE]
    assert waived == []


def test_no_failures_needs_no_waiver():
    remaining, waived = _waive([], skip_verify=True)
    assert remaining == []
    assert waived == []


@pytest.mark.parametrize(
    "reason",
    [
        "independent_review: unreviewable — no commit evidence found",
        "independent_review: UNREVIEWABLE — the stored verdict carries no summary",
    ],
)
def test_every_unreviewable_phrasing_the_gate_emits_is_waived(reason):
    """close_gates emits the word in two cases and two casings. A waiver matching only the
    quota phrasing would leave the others reaching for --force, which is the defect."""
    remaining, _ = _waive([reason], skip_verify=True)
    assert remaining == [], (
        f"{reason!r} was not waived. The first predicate matched 'unreviewable'"
        " case-sensitively, so the incomplete-record phrasing (UNREVIEWABLE) was left"
        " reaching for --force -- and an `or` in this assertion hid it."
    )
