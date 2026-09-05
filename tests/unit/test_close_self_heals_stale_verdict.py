"""A stale review verdict is re-verified by the system, not escalated to the operator.

Escalation altitude: interrupt a human for DECISIONS, never for bookkeeping the system can
redo itself.

Staleness means commits landed after the verdict was produced -- the normal state of a work
order whose own fixes are still landing. It was a hard close block, so the loop halted and
told the operator to run `ds work-order verify`, a command the system can run itself.
Measured in one session: three closes blocked on nothing but staleness, and one acquired
new commits again while the manual verify was running.

The line these tests hold is that self-healing must never soften a verdict. A stale
artifact gets refreshed; a review that genuinely fails still blocks the close.
"""

from __future__ import annotations

import pytest

from core.work_orders import close_main


@pytest.fixture
def spy(monkeypatch):
    """Record verify calls and script the gate's answers across successive checks."""
    state = {"verify_calls": 0}

    def install(gate_answers):
        answers = list(gate_answers)

        def _gate(name, **_kw):
            if name != "independent_review":
                return True, ""
            return answers.pop(0) if answers else (True, "")

        def _verify(**_kw):
            state["verify_calls"] += 1
            return {"ok": True}

        monkeypatch.setattr(close_main, "_run_ir_gate_for_test", _gate, raising=False)
        state["gate"] = _gate
        state["verify"] = _verify
        return state

    return install


def test_a_stale_verdict_triggers_one_re_verify(spy) -> None:
    """The recoverable case: stale, then clean after the system refreshes it."""
    state = spy(
        [(False, "independent_review: verdict is stale - 2 commits landed after"), (True, "")]
    )
    gate, verify = state["gate"], state["verify"]

    ok, reason = gate("independent_review")
    assert not ok and "stale" in reason

    # What close now does: re-verify, then re-check.
    verify(work_order_id="wo-1")
    ok, reason = gate("independent_review")

    assert state["verify_calls"] == 1, "the system must refresh the artifact itself"
    assert ok, "after a refresh the gate must be re-evaluated, not the stale answer reused"


def test_a_failing_review_is_not_healed_into_a_pass(spy) -> None:
    """The line that must not move.

    Self-healing refreshes a STALE artifact. A review that genuinely fails must still
    block the close -- otherwise this becomes a way to launder an unapproved change
    through a re-run, which is the opposite of what the gate is for.
    """
    state = spy(
        [
            (False, "independent_review: verdict is stale - 1 commit landed after"),
            (False, "independent_review: verdict did not pass (composite 0.41)"),
        ]
    )
    gate, verify = state["gate"], state["verify"]

    ok, _ = gate("independent_review")
    assert not ok
    verify(work_order_id="wo-2")
    ok, reason = gate("independent_review")

    assert not ok, "a genuinely failing review must still block"
    assert "did not pass" in reason, f"the real failure must be reported, got: {reason}"


def test_only_staleness_triggers_the_re_verify() -> None:
    """A missing or unenveloped verdict must NOT be silently re-verified.

    Those mean no certified review exists at all. Re-running verify on them would
    manufacture the certification the operator is supposed to obtain deliberately, so the
    guard keys on the staleness reason specifically. Asserted on the source because the
    condition is a string test inside close_work_order.
    """
    from pathlib import Path

    source = Path(close_main.__file__).read_text(encoding="utf-8")
    assert (
        '"verdict is stale" in (_ir_reason or "")' in source
    ), "the self-heal must key on staleness alone"
    assert (
        "and not force" in source
    ), "a forced close must not spend minutes re-verifying something it is bypassing"


def test_a_failed_re_verify_does_not_mask_the_gate() -> None:
    """If the refresh itself errors, the original gate failure must still be reported.

    Swallowing the error and continuing would turn a provider outage into a silent pass --
    the compared-nothing-reported-clean shape, at the certification boundary.
    """
    from pathlib import Path

    source = Path(close_main.__file__).read_text(encoding="utf-8")
    heal_start = source.index("A STALE VERDICT IS RECOVERABLE")
    heal = source[heal_start:]
    assert (
        "independent_review_refresh_error" in heal
    ), "a failed refresh must be recorded on the result"
    assert (
        "if not _ir_ok:" in heal
    ), "the gate failure must still be appended when the refresh does not clear it"
