"""A verdict must say when its TEST-CHECKs never ran.

WO 23327260. A grader on 2026-09-07 ended its verdict for WO 0a7abdfe with "Note also that
the tests were NOT executed here: the pytest run was denied approval, so pass/fail for the
TEST-CHECK criteria is unverified." True, honest, and buried in trailing prose -- the
verdict rendered as an ordinary graded verdict with per-task findings, so no reader
downstream could tell which parts rested on executed checks and which rested on reading.

The AC gate's whole purpose is that a criterion is EXECUTED rather than asserted. An
unexecuted TEST-CHECK is therefore the AC-rot defect wearing a verdict, and it belongs in
the same sentence as the verdict rather than in a note after it.

``record_test_execution`` already reported a ``basis`` of ``not_run_at_verify``. What it
could not say was WHICH checks had not run or WHY -- the per-check ``not_executed_reason``
existed and nothing aggregated it -- so an approval denied by a sandbox and a runner that
was never invoked were indistinguishable.
"""

from __future__ import annotations

from core.work_orders.close_shared import verdict_execution_note
from core.work_orders.verify_executor import record_test_execution

_TASKS = [{"acceptance_criteria": "TEST-CHECK: tests/unit/test_a.py::test_b"}]


def _check(**kw) -> dict:
    base = {"kind": "TEST-CHECK", "expr": "tests/unit/test_a.py::test_b", "executed": True}
    base.update(kw)
    return base


def test_a_verdict_says_when_its_checks_did_not_run():
    """The symptom check for WO 23327260, end to end: record it, then render it."""
    execution = record_test_execution(
        _TASKS,
        {"t": [_check(executed=False, not_executed_reason="the pytest run was denied approval")]},
    )
    assert execution["basis"] == "not_run_at_verify"
    assert execution[
        "unexecuted"
    ], "which checks did not run must be recorded, not just that some did not"
    assert execution["unexecuted"][0]["reason"] == "the pytest run was denied approval"

    note = verdict_execution_note({"test_execution": execution})
    assert "CHECKS NOT EXECUTED" in note
    assert "unverified" in note
    assert "denied approval" in note, "the reason must survive into what a reader sees"


def test_an_executed_verdict_says_nothing():
    """The control. A note that always appears is one a reader learns to skip, which is the
    same failure as the note that never appeared."""
    execution = record_test_execution(_TASKS, {"t": [_check(passed=True)]})
    assert execution["basis"] == "executed"
    assert execution["unexecuted"] == []
    assert verdict_execution_note({"test_execution": execution}) == ""


def test_a_work_order_registering_no_test_check_says_nothing():
    """No verdict on it could rest on execution, so nothing is being withheld."""
    execution = record_test_execution([{"acceptance_criteria": "Ship the thing."}], {})
    assert execution["basis"] == "none_registered"
    assert verdict_execution_note({"test_execution": execution}) == ""


def test_a_partially_executed_verdict_still_declares_the_gap():
    """One ran and one did not: the verdict is execution-backed for one criterion only.

    `basis` becomes "executed" as soon as anything ran, which is why the unexecuted LIST is
    the field that carries the gap -- reporting only the basis would call this fully backed.
    """
    execution = record_test_execution(
        [
            {"acceptance_criteria": "TEST-CHECK: tests/unit/test_a.py::test_b"},
            {"acceptance_criteria": "TEST-CHECK: tests/unit/test_c.py::test_d"},
        ],
        {
            "t1": [_check(passed=True)],
            "t2": [
                _check(
                    expr="tests/unit/test_c.py::test_d",
                    executed=False,
                    not_executed_reason="the command does not exist here",
                )
            ],
        },
    )
    assert execution["basis"] == "executed"
    assert len(execution["unexecuted"]) == 1
    assert execution["unexecuted"][0]["expr"] == "tests/unit/test_c.py::test_d"


def test_an_unexecuted_check_with_no_recorded_reason_still_says_so():
    """Absence of a reason must not read as absence of the problem."""
    execution = record_test_execution(_TASKS, {"t": [_check(executed=False)]})
    assert execution["unexecuted"][0]["reason"] == "no reason recorded"


def test_the_note_is_silent_on_a_verdict_with_no_execution_record():
    """A pre-field verdict must not be reported as unexecuted: absence of the record is not
    evidence the checks were skipped."""
    assert verdict_execution_note({}) == ""
    assert verdict_execution_note({"test_execution": None}) == ""
    assert verdict_execution_note({"test_execution": {}}) == ""


def test_the_close_refusal_carries_the_note():
    """Recording it is half; a reader has to SEE it in the message that refuses the close."""
    import inspect

    from core.work_orders import close_gates

    source = inspect.getsource(close_gates)
    assert "verdict_execution_note(verdict)" in source, (
        "the independent_review refusal does not carry the execution note, so the fact"
        " stays where it was: recorded and unread"
    )
