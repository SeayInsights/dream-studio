"""Review lane ``a-test-that-cannot-fail`` — the Falsifier.

THE QUESTION: this test is green. Show me it going red. What does it look like when the
thing it guards is broken?

WHY THIS SEAT EXISTS. It is the most productive defect family in this repo and, until now,
the only one with neither a gate nor a seat. Every instance was found by an independent
auditor, never by the suite that contained it:

    A non-mutation test hashed the live database's FILE BYTES before and after a run.
    Wrong in both directions for its whole life: it FAILED without a mutation, because
    WAL mode lets a benign read checkpoint the log into the main file; and it COULD NOT
    FAIL for the real reason, because `tests/conftest.py` redirects the database
    session-wide, so nothing inside pytest ever reaches the live file. Proved by
    mutation: with the override removed -- the exact defect -- a connection-recording
    version still passed.                                              (WO a9fa2368)

    A control test asserting a hand-typed table of booleans against itself, never
    executing the fixture it claimed to reproduce.                      (WO 5db3755e)

    Two tautologies -- "the shipped registry passes its own gate", "this repo has no
    unbounded per-item wait" -- both green under a checker mutated to report nothing.

    A coverage report and the executor sharing a PATTERN but each applying it. Deleting
    the report's own `.strip()` -- touching neither the pattern nor the executor -- left
    all 30 of its tests green while an indented `  TEST-CHECK: x` became a criterion the
    executor RUNS and the report calls prose.                           (WO eac7f657)

WHY GRADED AND NOT A DETECTOR — MEASURED, AND THE MEASUREMENT IS THE WHOLE ARGUMENT. Two
static shapes were prototyped across 6249 test functions: **79** have no assertion of any
kind, and **3** assert only on literals. Both counts are almost entirely legitimate -- the
79 are `tests/evals/test_dependency_chain.py`'s deliberate `*_unknown` / `*_untested`
markers, which exist to record what is NOT covered, and the 3 are intentional probes for
other gates (`trivial_pass_test.py`, `test_trivial_passing_probe`).

And decisively: **not one of the real instances above would have been found.** Every one of
them had assertions, on computed values, that read as thorough. The byte-hash test asserted
a hash comparison; the control table asserted booleans; the `.strip()` case had 30 passing
assertions. A detector for this lane would flag 82 legitimate tests and zero defects, which
is a wall and decoration at the same time.

The only reliable answer is to mutate the thing under test and watch, and that is a
reviewer's act rather than a gate's — which is exactly what a seat is for.

WHAT THIS TEST CAN HONESTLY ASSERT: that the fixture is a genuine instance — a test that
passes both against correct code and against code with the defect it claims to catch — and
that the lane is registered. Not that a grader catches it; stubbing a grader would only
test the stub.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

LANE_ID = "a-test-that-cannot-fail"
SEAT = "Test-integrity inquisitor"


#: THE THING UNDER TEST. A guard that is supposed to refuse an unsafe path.
def _guard(path: str) -> bool:
    """Correct: refuses anything escaping the root."""
    return ".." not in path


def _guard_broken(path: str) -> bool:
    """The defect: admits everything. A review's job is to notice the test cannot tell."""
    return True


#: THE CEREMONY. Reads as a real test of `_guard`, and cannot fail.
#:
#: Two things make it vacuous, and both are ordinary mistakes rather than contrivances: it
#: only ever passes SAFE inputs, so the refusing branch is never exercised; and it asserts
#: on a value it constructed itself rather than on the guard's answer.
def _ceremony(guard) -> None:
    allowed = ["core/x.py", "docs/y.md"]
    results = [guard(p) for p in allowed]
    assert len(results) == 2
    assert all(isinstance(r, bool) for r in results)
    assert allowed == ["core/x.py", "docs/y.md"]


#: THE REAL TEST. Same subject, and it goes red the moment the guard stops refusing.
def _falsifiable(guard) -> None:
    assert guard("core/x.py") is True
    assert guard("../../etc/passwd") is False


def _lane() -> dict:
    data = yaml.safe_load(
        (REPO_ROOT / "canonical" / "review_lanes.yml").read_text(encoding="utf-8")
    )
    return next(lane for lane in data["lanes"] if lane["id"] == LANE_ID)


def _passes(check, guard) -> bool:
    try:
        check(guard)
        return True
    except AssertionError:
        return False


def test_the_ceremony_passes_against_the_defect_it_claims_to_catch():
    """THE DEFINITION OF THE LANE, reproduced rather than described.

    A test is ceremony when its verdict does not depend on the thing it tests. Here the
    same assertions pass against a guard that refuses nothing — so a reviewer reading
    "green" learns nothing about whether the guard works.
    """
    assert _passes(_ceremony, _guard), "the fixture must pass against correct code"
    assert _passes(
        _ceremony, _guard_broken
    ), "and against the defect — that is what makes it ceremony rather than a test"


def test_the_falsifiable_version_goes_red_on_the_same_defect():
    """The positive control. Without it, this fixture would only show that SOME test passes
    under a mutation, not that a better test of the same subject would not — and the lane
    would be indistinguishable from "mutation testing is impossible here"."""
    assert _passes(_falsifiable, _guard), "it must pass against correct code"
    assert not _passes(
        _falsifiable, _guard_broken
    ), "and fail against the defect, which the ceremony does not"


def test_the_two_differ_only_in_what_they_assert_on():
    """The distinction is not effort or length. The ceremony has MORE assertions than the
    real test — three against two — which is why "it has assertions" and "it can fail" get
    confused, and why a static detector measured 79 no-assertion tests and found none of the
    real instances."""
    import inspect

    ceremony = inspect.getsource(_ceremony)
    real = inspect.getsource(_falsifiable)

    assert ceremony.count("assert ") > real.count("assert "), (
        "the vacuous fixture must not be the thinner one, or this reads as a lesson about"
        " test coverage instead of about what the assertions are ON"
    )
    # The ceremony never passes an input the guard should REFUSE. That is the whole defect.
    assert ".." not in ceremony, "the ceremony must never exercise the refusing branch"
    assert ".." in real, "the real test must exercise it"


def test_the_lane_is_registered_and_declares_why_it_is_graded():
    lane = _lane()
    assert lane["seat"] == SEAT, lane["seat"]
    assert lane["eval"] == "tests/evals/" + Path(__file__).name
    assert lane["question"].strip().endswith("?"), lane["question"]

    measurement = " ".join(str(lane["measurement"]).split())
    # The counts that rejected a detector belong in the registry, so the next author reads
    # them before rebuilding the same wall.
    assert "6249" in measurement, "the population measured must be recorded"
    assert "79" in measurement, "the no-assertion count must be recorded"
    assert (
        "zero" in measurement.lower() or "none" in measurement.lower()
    ), "the load-bearing half is that the static shapes found NONE of the real instances"
