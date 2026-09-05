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
    assert (
        source.count("_MAX_GRADER_ATTEMPTS") >= 3
    ), "both the serial and parallel paths must bound their attempts by the same cap"
    parallel_start = source.index("def _run_graders_parallel")
    parallel = source[parallel_start:]
    assert "_MAX_GRADER_ATTEMPTS" in parallel, "the parallel path still has a single retry"
    assert (
        "role_collect_timeout(name) if timed_out" in parallel
    ), "the parallel path must also keep the full budget after a timeout"
