"""WO 5db3755e: five reviewers' lenses must be enforced, not written down.

THE REQUEST. Five named reviewers on a platform/gateway pass each found a defect nobody else
did, and each found it by asking one repeatable question. Those questions lived in their
heads. Putting them in the review skill's prose would put them where the operator has
already said guidance goes to die: "a lot of prose laid on top of each other as suggestions
with no rules, evals, or really any real test that doing anything they are supposed to."

So `canonical/review_lanes.yml` holds them under the same enforce-or-declare contract
`canonical/rules.yml` already runs on, and `core/gates/review_lane_registry.py` refuses a
lane that is none of a detector, an eval, or a declared judgment with a reason.

MOST OF THESE TESTS CONSTRUCT LANES AND SOURCE and hand them to the checker, rather than
editing the real registry. Mutating a real input tests the input; it does not test the
checker. The tests that DO read the real registry or the real tree say why in their own
docstrings.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.gates.aggregate_deadline import offenders_in_text as deadline_offenders
from core.gates.branch_freshness import measure as branch_measure
from core.gates import review_lane_registry
from core.gates.review_lane_registry import REGISTRY
from core.gates.review_lane_registry import run as registry_run
from core.gates.untested_fallback import fallback_symbols
from core.gates.untested_fallback import offenders_in_text as fallback_offenders

REPO_ROOT = Path(__file__).resolve().parents[2]

NL = chr(10)


def _lanes() -> list[dict]:
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["lanes"]


def _gate_still_detects() -> bool:
    """Whether the registry gate reports a lane that is plainly advice.

    The positive control for `test_the_shipped_registry_passes_its_own_gate`: a clean result
    on today's registry means nothing unless the gate can still fail.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        registry = Path(tmp) / "review_lanes.yml"
        registry.write_text(
            yaml.safe_dump({"version": 1, "lanes": [{"id": "advice-only"}]}), encoding="utf-8"
        )
        original = review_lane_registry.REGISTRY
        try:
            review_lane_registry.REGISTRY = registry
            return review_lane_registry.run()["status"] == "fail"
        finally:
            review_lane_registry.REGISTRY = original


# ── the registry contract ────────────────────────────────────────────────────


def test_the_shipped_registry_passes_its_own_gate():
    """A registry that fails its own gate would be a rule nobody can keep green.

    Read against the real file on purpose: the compatibility claim is about THIS registry,
    and a fixture could drift away from it.
    """
    result = registry_run()
    assert result["status"] == "pass", result["errors"]
    assert result["lane_count"] >= 6, result

    # POSITIVE CONTROL. An audit made `run()` swallow its own errors and this test still
    # passed -- "the registry is clean today" is satisfied by a gate that reports nothing.
    # The parametrized cases below cover detection, but this test read alone was a
    # tautology, so it now proves the gate can still speak.
    assert _gate_still_detects(), (
        "the registry gate reported nothing for a lane that is plainly advice, so a clean"
        " result here proves nothing"
    )


def test_every_lane_has_exactly_one_enforcement_key():
    """The contract's whole content. A lane with none is advice; a lane with two has not
    decided which mechanism actually answers it."""
    for lane in _lanes():
        present = [key for key in ("detector", "eval", "judgment") if key in lane]
        assert len(present) == 1, f"{lane.get('id')}: {present}"


def test_every_lane_names_the_finding_it_came_from():
    """A lane with no precedent is a hunch with a registry entry. The finding is the only
    thing that tells a later reader whether the question is still worth asking."""
    for lane in _lanes():
        assert len(str(lane.get("precedent") or "").strip()) >= 40, lane.get("id")


def test_every_lane_records_why_it_is_a_detector_or_not():
    """The measurement is the load-bearing part of this registry.

    A detector that fires on hundreds of sites is a wall someone switches off; one that
    fires on nothing is decoration. Every lane carries the count it produced against this
    tree, so the next person does not re-derive it -- and so a lane claiming "too hard"
    has to show its work.
    """
    for lane in _lanes():
        assert len(str(lane.get("measurement") or "").strip()) >= 40, lane.get("id")


def test_every_lane_is_held_by_a_seat():
    """A seat says what the lane watches; a handle says who happened to find it.

    These lanes arrived from an external review pass carrying their finders' real names --
    other people's handles in a repo with a publication-readiness gate, and a name that
    describes nothing to a later reader. The seat is a closed set in the gate, so a lane
    cannot be added under somebody's name.
    """
    seats = {lane.get("seat") for lane in _lanes()}
    assert seats <= review_lane_registry._SEATS, seats - review_lane_registry._SEATS
    # THE PROPERTY IS DISTINCTNESS, NOT A COUNT. This asserted `== 5` and broke the
    # moment a seventh lane arrived with a sixth seat -- a true statement about the
    # registry of the day, pinned as though it were the rule. What matters is that the
    # lanes do not collapse onto one seat, which would mean the seats describe nothing.
    assert len(seats) >= 2, f"every lane collapsed onto {seats}"
    assert len(seats) <= len(review_lane_registry._SEATS), seats


def test_a_lane_seated_under_a_persons_name_is_refused(monkeypatch, tmp_path):
    """The enforcement, not just the convention."""
    registry = tmp_path / "review_lanes.yml"
    registry.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "lanes": [
                    {
                        "id": "someones-lane",
                        "seat": "jdoe",
                        "question": "q" * 50,
                        "signature": "s" * 50,
                        "precedent": "p" * 50,
                        "measurement": "m" * 50,
                        "judgment": True,
                        "why": "w" * 50,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("core.gates.review_lane_registry.REGISTRY", registry)

    result = registry_run()

    assert result["status"] == "fail"
    assert any("is not one of" in error for error in result["errors"]), result["errors"]


def test_the_review_skill_names_every_seated_lane():
    """A lane the reviewer never sees is a lane nobody asks.

    Stage 2 of the review skill enumerates the lanes; adding one to the registry without
    surfacing it there is the drift that made the eight original lenses the whole story.
    Checks the projection too, since an install reads that copy and not this one.
    """
    canonical = REPO_ROOT / "canonical" / "skills" / "core" / "modes" / "review" / "SKILL.md"
    projected = (
        REPO_ROOT / "dist" / "plugin" / "skills" / "ds-core" / "modes" / "review" / "SKILL.md"
    )
    canonical_text = canonical.read_text(encoding="utf-8")

    for lane in _lanes():
        seat = lane["seat"]
        assert seat in canonical_text, f"{seat} is not named in the review skill"

    if projected.is_file():
        assert projected.read_text(encoding="utf-8") == canonical_text, (
            "the projected review skill is stale -- an install would read a different lane"
            " list from the one this repo enforces"
        )


@pytest.mark.parametrize(
    ("lane", "expected_fragment"),
    [
        (
            {
                "id": "a",
                "question": "q" * 50,
                "signature": "s" * 50,
                "precedent": "p" * 50,
                "measurement": "m" * 50,
            },
            "declares no detector",
        ),
        (
            {
                "id": "b",
                "question": "q" * 50,
                "signature": "s" * 50,
                "precedent": "p" * 50,
                "detector": "py -m core.gates.branch_freshness",
                "judgment": True,
            },
            "exactly one must answer",
        ),
        (
            {
                "id": "c",
                "question": "q" * 50,
                "signature": "s" * 50,
                "precedent": "p" * 50,
                "judgment": True,
                "why": "too hard",
            },
            "no usable `why`",
        ),
        (
            {
                "id": "d",
                "question": "q" * 50,
                "signature": "s" * 50,
                "precedent": "p" * 50,
                "eval": "tests/evals/does_not_exist.py",
            },
            "does not exist",
        ),
        (
            {
                "id": "e",
                "question": "q" * 50,
                "signature": "s" * 50,
                "precedent": "p" * 50,
                "detector": "py -m core.gates.no_such_module",
            },
            "does not import",
        ),
        (
            {
                "id": "g",
                "question": "q" * 50,
                "signature": "s" * 50,
                "precedent": "p" * 50,
                "measurement": "m" * 50,
                "judgment": False,
                "why": "w" * 50,
            },
            "must be literally true",
        ),
        (
            {
                "id": "f",
                "question": "short",
                "signature": "s" * 50,
                "precedent": "p" * 50,
                "judgment": True,
                "why": "w" * 50,
            },
            "`question` is missing or shorter",
        ),
    ],
)
def test_a_lane_that_is_really_advice_is_refused(lane, expected_fragment, monkeypatch, tmp_path):
    """CONSTRUCTED LANES, one per way a lane can fail to be enforced.

    Each of these is a way a registry entry can look complete and enforce nothing: no
    mechanism, two mechanisms, a shrug for a reason, a grader that is not there, a detector
    that does not import, and a question too short to be a question.
    """
    registry = tmp_path / "review_lanes.yml"
    registry.write_text(yaml.safe_dump({"version": 1, "lanes": [lane]}), encoding="utf-8")
    monkeypatch.setattr("core.gates.review_lane_registry.REGISTRY", registry)

    result = registry_run()

    assert result["status"] == "fail", result
    assert any(expected_fragment in error for error in result["errors"]), result["errors"]


def test_a_registry_that_is_not_there_fails_rather_than_passing(monkeypatch, tmp_path):
    """A check that could not run must not read like a check that found nothing."""
    monkeypatch.setattr("core.gates.review_lane_registry.REGISTRY", tmp_path / "absent.yml")
    result = registry_run()
    assert result["status"] == "fail"
    assert any("could not be read" in error for error in result["errors"])


# ── lane: a per-item wait with no aggregate deadline (the Machinist, gw#849) ─────


def test_the_multiplication_shape_is_reported():
    """gw#849 itself: a per-item retry inside a loop over a data-dependent count.

    Every wait was bounded. Nothing bounded the product: 2 x 0.5s inside a loop over
    equipped skills is ~20s at 20 skills, past the 30s timeout the module cited -- in a
    module that had already batch-capped its OTHER loop for exactly this reason.
    """
    source = (
        "for sid in ids:"
        + NL
        + "    for attempt in range(2):"
        + NL
        + "        time.sleep(0.5)"
        + NL
    )
    offenders = deadline_offenders(source, "delivery.py")
    assert offenders, "the multiplication shape was not reported"
    assert "bounds the TOTAL" in offenders[0]["message"]


def test_an_outer_loop_that_watches_the_total_is_clean():
    """The other direction. Without this the test above would pass against a checker that
    reports every nested loop."""
    source = (
        "deadline = monotonic() + 5.0"
        + NL
        + "for sid in ids:"
        + NL
        + "    if monotonic() > deadline:"
        + NL
        + "        break"
        + NL
        + "    for attempt in range(2):"
        + NL
        + "        time.sleep(0.5)"
        + NL
    )
    assert deadline_offenders(source, "delivery.py") == []


def test_a_bounded_single_retry_is_clean():
    """THE MEASURED FALSE POSITIVE THAT SHARPENED THE PREDICATE.

    A first cut asked only "is there a sleep in a loop, in a module that defines a budget
    constant". That found exactly one candidate in this repo -- core/work_orders/
    artifacts.py:216 -- and reading it showed _LOCK_ATTEMPTS=4 with a 0.15s backoff: 0.90s
    worst case, on a single artifact write, not inside any outer per-item loop. Bounded,
    and not the shape. Requiring NESTING dropped the tree to zero.
    """
    source = "for attempt in range(4):" + NL + "    time.sleep(0.15 * (attempt + 1))" + NL
    assert deadline_offenders(source, "artifacts.py") == []


def test_an_awaited_sleep_counts():
    """`asyncio.sleep` stalls a loop exactly as `time.sleep` does, and the finding was about
    a synchronous session event loop."""
    source = (
        "for sid in ids:" + NL + "    while pending:" + NL + "        await asyncio.sleep(0.5)" + NL
    )
    assert deadline_offenders(source, "delivery.py")


def test_an_exemption_needs_a_usable_reason():
    """An escape hatch without a mandatory reason becomes the norm."""
    declared = (
        "# aggregate-deadline: ids is capped at three by the caller's schema constraint"
        + NL
        + "for sid in ids:"
        + NL
        + "    for a in range(2):"
        + NL
        + "        time.sleep(0.5)"
        + NL
    )
    assert deadline_offenders(declared, "delivery.py") == []

    shrug = declared.replace("ids is capped at three by the caller's schema constraint", "fine")
    assert deadline_offenders(shrug, "delivery.py")


def test_this_repo_has_no_unbounded_per_item_wait():
    """Measured 0 after requiring nesting, which is why this lane runs whole-tree rather
    than diff-scoped. A gate that starts at zero can stay at zero."""
    from core.gates.aggregate_deadline import run as deadline_run

    result = deadline_run()
    assert result["status"] == "pass", result["offenders"]
    assert result["modules_scanned"] > 500, result

    # POSITIVE CONTROL. An audit forced `offenders_in_text` to return [] and this test still
    # passed, because a clean tree and a neutered detector are indistinguishable on today's
    # code. Clean has to mean looked-and-found-nothing.
    probe = (
        "for sid in ids:"
        + NL
        + "    for attempt in range(2):"
        + NL
        + "        time.sleep(0.5)"
        + NL
    )
    assert deadline_offenders(probe, "probe.py"), (
        "the detector found nothing in the gw#849 shape itself, so a clean tree proves" " nothing"
    )


# ── lane: an untested fallback lane (the Machinist, gw#858) ─────────────────────


def test_a_fallback_no_test_mentions_is_reported():
    """gw#858: `fallback_lock` had zero test hits while every ack test ran the flock path."""
    source = "def fallback_lock(path):" + NL + "    return _thread_lock(path)" + NL
    offenders = fallback_offenders(source, "locking.py", test_corpus="")
    assert offenders, "an unreferenced fallback was not reported"
    assert "no test mentions it" in offenders[0]["message"]


def test_a_fallback_a_test_mentions_is_clean():
    """The discriminating half: without it the test above would pass against a checker that
    reports every fallback whether or not it is exercised."""
    source = "def fallback_lock(path):" + NL + "    return _thread_lock(path)" + NL
    corpus = "def test_it():" + NL + "    assert fallback_lock('/tmp/x')" + NL
    assert fallback_offenders(source, "locking.py", test_corpus=corpus) == []


def test_a_definition_inside_an_import_handler_is_a_fallback_whatever_it_is_called():
    """Named detection alone would miss the commonest shape: a shim defined because the
    real dependency is absent, given an ordinary name."""
    source = (
        "try:"
        + NL
        + "    import fcntl"
        + NL
        + "except ImportError:"
        + NL
        + "    def take_lock(path):"
        + NL
        + "        return None"
        + NL
    )
    names = {name for name, _line, _why in fallback_symbols(source)}
    assert "take_lock" in names, names


def test_a_declared_untestable_lane_is_accepted_with_a_reason():
    source = (
        "# untested-fallback: only reachable on a filesystem without flock, absent in CI"
        + NL
        + "def fallback_lock(path):"
        + NL
        + "    return None"
        + NL
    )
    assert fallback_offenders(source, "locking.py", test_corpus="") == []

    shrug = source.replace("only reachable on a filesystem without flock, absent in CI", "todo")
    assert fallback_offenders(shrug, "locking.py", test_corpus="")


# ── lane: a branch behind its base (the Surveyor) ───────────────────────────


def test_branch_distance_is_measured_against_the_real_repository():
    """Drives the surface rather than reading this module's source. eugene's finding was
    that four PRs trial-merged CLEAN at 5 and 38 commits behind -- a clean trial-merge says
    the texts do not collide, not that the review read the tree that will ship."""
    result = branch_measure()
    if not result.get("measured"):
        pytest.skip(f"distance not measurable here: {result.get('reason')}")
    assert isinstance(result["behind"], int)
    assert isinstance(result["ahead"], int)
    assert result["notable"] is (result["behind"] >= 5)


def test_an_unresolvable_base_is_reported_not_silently_passed():
    """A check that could not run must say so. Silence from a check that never ran is
    indistinguishable from a pass, which is the fail-open shape `fail_open_probe` guards."""
    result = branch_measure(base_ref="refs/heads/no-such-base-ref-anywhere")
    assert result["measured"] is False
    assert "does not resolve" in result["reason"]
