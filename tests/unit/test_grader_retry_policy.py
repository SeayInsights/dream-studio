"""A grader miss is retried up to 20 times, and a timeout keeps its full budget.

Operator rule: run up to 20 attempts looking for one clean verdict.

Measured over one session: FOUR grader timeouts to one success, every one at the 360s
collect budget, each leaving a work order uncloseable behind an
``independent_review: unreviewable`` gate. Two things were wrong.

* There was exactly ONE retry. On a flaky provider that is a coin flip, not a policy.
* The retry was given a SHORTER budget than the call that just timed out -- 60s against
  the 360s that had already expired. A timeout means the call needed MORE time, so the
  single retry it got was near-certain to expire too. That inversion is why four
  consecutive timeouts never recovered.

These drive the real ``collect_grader_with_retry`` with a stubbed spawn/collect, so the
attempt count and the budget chosen per miss are observed rather than assumed.
"""

from __future__ import annotations

import pytest

from core.work_orders import verify_graders


@pytest.fixture
def stub(monkeypatch):
    """Replace spawn/collect so each attempt's outcome and budget are controllable."""
    calls: list[int] = []

    monkeypatch.setattr(verify_graders, "_spawn_grader", lambda *a, **k: object())

    def install(outcomes):
        seq = list(outcomes)

        def _collect(_proc, timeout=None):
            calls.append(timeout)
            outcome = seq.pop(0) if seq else {"verdict": "clean"}
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        monkeypatch.setattr(verify_graders, "_collect_grader", _collect)
        return calls

    return install


def test_a_transient_miss_is_retried_until_a_clean_verdict(stub) -> None:
    """Three misses then a clean answer: the clean answer is what comes back."""
    calls = stub(
        [
            {"unreviewable": True, "reason": "grader_no_summary"},
            {"unreviewable": True, "reason": "grader_no_summary"},
            {"_grader_error": "not json"},
            {"verdict": "clean", "completion_score": 1.0},
        ]
    )
    result = verify_graders.collect_grader_with_retry("prompt", None, role="completion")

    assert result.get("verdict") == "clean", result
    assert result.get("grader_attempts") == 4, "the attempt count must be reported"
    assert len(calls) == 4


def test_a_timeout_keeps_the_full_collect_budget(stub) -> None:
    """The inversion that made four consecutive timeouts unrecoverable.

    The retry budget exists for a formatting flake, where a short second look suffices.
    Applying it to a timeout hands the call LESS time than the one that just expired.
    """
    timeout_exc = Exception("Command '['claude', '--print']' timed out after 360 seconds")
    calls = stub([timeout_exc, {"verdict": "clean"}])
    verify_graders.collect_grader_with_retry("prompt", None, role="completion")

    full = verify_graders.role_collect_timeout("completion")
    assert calls[1] == full, (
        f"a timeout retry was given {calls[1]}s after {full}s expired; a call that ran out "
        "of time must not be handed less time"
    )


def test_a_formatting_flake_uses_the_shorter_retry_budget(stub) -> None:
    """The counterpart: without it, every miss would take the long window."""
    calls = stub([{"_grader_error": "replied in prose"}, {"verdict": "clean"}])
    verify_graders.collect_grader_with_retry("prompt", None, role="completion")

    assert calls[1] == verify_graders.role_retry_timeout("completion")


def test_attempts_are_capped(stub) -> None:
    """A provider that never answers must not retry forever."""
    calls = stub([{"unreviewable": True, "reason": "grader_no_summary"}] * 40)
    result = verify_graders.collect_grader_with_retry("prompt", None, role="completion")

    assert len(calls) == verify_graders._MAX_GRADER_ATTEMPTS
    assert result.get("unreviewable") is True, "an exhausted retry stays unreviewable"
    assert result.get("grader_attempts") == verify_graders._MAX_GRADER_ATTEMPTS


def test_a_missing_cli_is_not_retried(stub) -> None:
    """A re-spawn cannot conjure a missing binary; retrying 20 times would waste minutes."""
    calls = stub([{"unreviewable": True, "reason": "grader_cli_unavailable"}])
    verify_graders.collect_grader_with_retry("prompt", None, role="completion")

    assert len(calls) == 1, "a structurally-absent provider must fail fast"


def test_a_clean_first_answer_is_not_retried(stub) -> None:
    """Guards against a loop that retries regardless, burning 20 provider calls per grade."""
    calls = stub([{"verdict": "clean"}])
    result = verify_graders.collect_grader_with_retry("prompt", None, role="completion")

    assert len(calls) == 1
    assert "grader_attempts" not in result, "a first-time success reports no attempt count"


def test_the_parallel_path_shares_the_policy() -> None:
    """The live `ds work-order verify` takes the parallel path, not the serial one.

    Fixing only ``collect_grader_with_retry`` would have left every real verify on a
    single retry -- fixed-in-one-branch-not-its-sibling, the shape found four times this
    session. Asserted on the source because the parallel path spawns a real process pool.
    """
    from pathlib import Path

    source = Path(verify_graders.__file__).read_text(encoding="utf-8")
    serial_start = source.index("def collect_grader_with_retry")
    parallel_start = source.index("def _run_graders_parallel")
    serial = source[serial_start:parallel_start]
    parallel = source[parallel_start:]

    # Both ceilings now live in ONE helper that both paths call, which is stronger than
    # each path spelling the cap itself: a change to the policy cannot reach one path and
    # miss the other. This test previously asserted the literal _MAX_GRADER_ATTEMPTS
    # appeared inside each loop -- true of the old copy-paste shape, and stale the moment
    # the policy was shared.
    for name, chunk in (("serial", serial), ("parallel", parallel)):
        assert "_retry_budget_exhausted(started, attempts)" in chunk, (
            f"the {name} path does not consult the shared retry budget, so the attempt and"
            " time ceilings can drift apart between the two paths"
        )
    assert (
        "role_collect_timeout(name) if timed_out" in parallel
    ), "the parallel path must also keep the full budget after a timeout"
    assert (
        "role_collect_timeout(role) if timed_out" in serial
    ), "the serial path must also keep the full budget after a timeout"


# --------------------------------------------------------------------------------------
# The WALL-CLOCK ceiling. The attempt count alone is not a budget: 20 attempts x a 360s
# collect window is two hours on ONE role, and a work order runs several. Measured on the
# close sweep of 2026-09-07, one verify sat past 20 minutes on a role that kept timing out.
# --------------------------------------------------------------------------------------


def test_a_time_ceiling_exists_alongside_the_attempt_ceiling():
    assert verify_graders._MAX_GRADER_ATTEMPTS == 20, "the operator's rule is 20 attempts"
    assert verify_graders._MAX_GRADER_RETRY_SECONDS > 0, (
        "20 attempts at the full collect budget is two hours on one role; the attempt count"
        " alone is not a budget"
    )


def test_the_attempt_ceiling_stops_the_retrying_and_says_so():
    exhausted = verify_graders._retry_budget_exhausted(
        __import__("time").monotonic(), verify_graders._MAX_GRADER_ATTEMPTS
    )
    assert exhausted is not None
    assert "attempt ceiling" in exhausted


def test_the_time_ceiling_stops_the_retrying_and_says_so():
    long_ago = __import__("time").monotonic() - (verify_graders._MAX_GRADER_RETRY_SECONDS + 1)
    exhausted = verify_graders._retry_budget_exhausted(long_ago, 2)
    assert exhausted is not None
    assert "time ceiling" in exhausted
    assert "2 attempt" in exhausted, "the reason must say how many attempts were spent"


def test_there_is_room_while_both_ceilings_are_unmet():
    assert verify_graders._retry_budget_exhausted(__import__("time").monotonic(), 1) is None


def test_giving_up_is_recorded_on_the_result_not_left_silent():
    """A stall reported as a stall is actionable; a stall reported as nothing is not."""
    calls = {"n": 0}

    def _never_succeeds(prompt, profile, *, timeout):
        calls["n"] += 1
        return None

    monkey = pytest.MonkeyPatch()
    try:
        monkey.setattr(verify_graders, "_retry_grader_once", _never_succeeds)
        monkey.setattr(verify_graders, "_MAX_GRADER_ATTEMPTS", 3)

        class _Proc:
            pass

        monkey.setattr(
            verify_graders,
            "_collect_grader",
            lambda proc, timeout: {"unreviewable": True, "_grader_error": "timed out"},
        )
        monkey.setattr(verify_graders, "_spawn_grader", lambda *a, **k: _Proc())
        result = verify_graders.collect_grader_with_retry("p", None, role="completion")
    finally:
        monkey.undo()

    assert result.get("grader_attempts") == 3
    assert "attempt ceiling" in str(result.get("grader_retry_stopped_by"))
    assert calls["n"] == 2, "it must stop retrying at the ceiling, not run past it"
