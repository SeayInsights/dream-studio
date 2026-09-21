"""Every gate that runs leaves a record, not only the ones that block.

The authority held 649 `gate.pre_push.failed`, 408 `gate.bypassed` and zero
passes. That is a numerator with no denominator: nine of the seventeen wired
gates have never appeared in a failure record, and nothing could say whether
those nine prevent something or are dead. "How much of this is ceremony" was
unanswerable from data for exactly this reason.

Advisory failures were worse than unmeasured -- the run loop read
`if result.is_advisory: pass`, so the tier whose entire purpose is to surface a
signal without blocking emitted nothing at all.
"""

from __future__ import annotations

import pytest

from canonical.events.types import EventType
from core.gates import pre_push


def _result(gate_id="g", passed=True, advisory=False, exit_code=0):
    return pre_push.GateResult(
        gate_id=gate_id,
        passed=passed,
        exit_code=exit_code,
        duration_seconds=1.234,
        stdout_tail="",
        stderr_tail="",
        fail_hint="",
        tier="advisory" if advisory else "blocking",
    )


@pytest.fixture
def captured(monkeypatch):
    sent: list = []
    monkeypatch.setattr(
        "emitters.shared.spool_writer.write_envelopes", lambda envs: sent.extend(envs)
    )
    return sent


@pytest.mark.parametrize(
    "passed,advisory,expected",
    [
        (True, False, "passed"),
        (False, False, "failed"),
        (False, True, "advisory_failed"),
        (True, True, "passed"),
    ],
)
def test_outcome_is_recorded_for_every_result(captured, passed, advisory, expected):
    pre_push.emit_gate_outcome_event(_result(passed=passed, advisory=advisory))
    assert len(captured) == 1
    env = captured[0]
    assert env.event_type == EventType.GATE_PRE_PUSH_COMPLETED.value
    assert env.payload["outcome"] == expected
    assert env.payload["gate_id"] == "g"


def test_a_passing_gate_is_recorded(captured):
    """The whole point. Without this row there is no denominator, and a gate
    that never fails cannot be told apart from a gate that never runs."""
    pre_push.emit_gate_outcome_event(_result(gate_id="rule1", passed=True))
    assert captured[0].payload["passed"] is True
    assert captured[0].payload["gate_id"] == "rule1"


def test_an_advisory_failure_is_recorded(captured):
    """Previously emitted nothing whatsoever."""
    pre_push.emit_gate_outcome_event(
        _result(gate_id="review-lanes-drift", passed=False, advisory=True)
    )
    assert captured[0].payload["outcome"] == "advisory_failed"
    assert captured[0].payload["advisory"] is True


def test_emission_failure_never_raises(monkeypatch, capsys):
    """A telemetry write must not decide whether a push is allowed. The gate
    results govern the exit code; this is bookkeeping beside them."""

    def _boom(_):
        raise OSError("spool unavailable")

    monkeypatch.setattr("emitters.shared.spool_writer.write_envelopes", _boom)
    pre_push.emit_gate_outcome_event(_result())  # must not raise
    assert "spool write failed" in capsys.readouterr().err


def test_the_failure_event_still_fires_unchanged(captured):
    """649 rows of gate.pre_push.failed and whatever reads them keep working --
    the outcome event is emitted beside it, not in place of it."""
    pre_push.emit_gate_failure_event(_result(passed=False, exit_code=1))
    assert captured[0].event_type == EventType.GATE_PRE_PUSH_FAILED.value
