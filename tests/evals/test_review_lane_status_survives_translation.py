"""Review lane ``a-status-the-far-end-does-not-handle`` — the Interpreter.

THE FINDING, the second half of the same review pass. ``measure_network_reliability``
emits ``not_applicable`` today, for agents that do not heartbeat. The radar renderer
branched on the statuses it knew and let everything else fall through to a numeric zero,
so ``not_applicable`` drew a normal-weight spoke to the centre vertex — **reading as 0%
uptime** for an agent whose uptime was never measurable.

The finder's diagnosis again names the gap precisely: *"I checked that the six axis keys
matched the server and never asked what the statuses render as."* The KEYS were verified
against the producer. The VOCABULARY inside those keys was not. A reviewer who confirms
the shape of a contract and stops has verified the envelope, not the meaning.

WHY THIS IS A SEPARATE LANE FROM ``a-produced-value-with-no-reader``, though both sit with
the same seat: there the consumer does not exist, and the remedy is to add one. Here the
consumer exists and is wrong, and the remedy is to make its branch set match the
producer's vocabulary — or to fail loudly on a member it does not know. Folding them into
one lane would give it two questions and one answer, which is how a lane stops being
falsifiable.

THE DEFECT SHAPE IN ONE LINE: the producer's vocabulary is larger than the consumer's
branches, and the consumer's default is a MEMBER OF THE SAME VOCABULARY rather than an
error. ``not_applicable`` becoming 0% is not a crash and not a blank — it is a different,
plausible reading. Same family as the sibling lane: the wrong answer is indistinguishable
from a legitimate one.

WHY GRADED. The vocabulary is knowable statically in a single-language, single-repo case,
but the instance that produced this lane crossed a language boundary — a Python measure
function and a TypeScript renderer — and a member can also arrive from a database column,
a config file, or a provider's API without appearing as a literal anywhere. A detector
restricted to the cases where both sides are Python literals would pass on the very shape
that produced the finding, which reads like enforcement and is not. The count that decided
it is recorded on the sibling lane: 2108 keys produced, 588 unread, 198 files — the same
analysis that cannot see a non-Python consumer cannot see a non-Python branch set either.

WHAT THIS TEST CAN HONESTLY ASSERT: that the fixture is a genuine instance — a producer
emitting a member the consumer has no branch for, and a default that means something else
in the same vocabulary — and that the lane is registered. Not that a grader catches it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

LANE_ID = "a-status-the-far-end-does-not-handle"
SEAT = "Failure semantics"

#: THE PRODUCER's full vocabulary. `not_applicable` is emitted today, not hypothetically.
PRODUCER = """
def measure_network_reliability(agent):
    if not agent.heartbeats_enabled:
        return {"status": "not_applicable", "uptime": None}
    if agent.missed_beats == 0:
        return {"status": "ok", "uptime": 1.0}
    if agent.missed_beats < agent.threshold:
        return {"status": "degraded", "uptime": agent.uptime_ratio}
    return {"status": "down", "uptime": agent.uptime_ratio}
"""

#: THE CONSUMER. Branches on three of four, and the fallback is a NUMBER, not an error.
CONSUMER = """
def spoke_for(reading):
    status = reading["status"]
    if status == "ok":
        return {"weight": "normal", "radius": 1.0}
    if status == "degraded":
        return {"weight": "normal", "radius": reading["uptime"]}
    if status == "down":
        return {"weight": "normal", "radius": 0.0}
    # Anything else lands here. `not_applicable` draws to the centre and reads as 0%.
    return {"weight": "normal", "radius": 0.0}
"""


def _lane() -> dict:
    data = yaml.safe_load(
        (REPO_ROOT / "canonical" / "review_lanes.yml").read_text(encoding="utf-8")
    )
    return next(lane for lane in data["lanes"] if lane["id"] == LANE_ID)


def _emitted_statuses(source: str) -> set[str]:
    """Every value the producer assigns to a "status" key in a returned dict."""
    tree = ast.parse(source)
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            for key, value in zip(node.value.keys, node.value.values):
                if (
                    isinstance(key, ast.Constant)
                    and key.value == "status"
                    and isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                ):
                    out.add(value.value)
    return out


def _handled_statuses(source: str) -> set[str]:
    """Every status the consumer explicitly compares against."""
    tree = ast.parse(source)
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for comparator in node.comparators:
                if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                    out.add(comparator.value)
    return out


def test_the_producer_emits_a_status_the_consumer_has_no_branch_for():
    emitted = _emitted_statuses(PRODUCER)
    handled = _handled_statuses(CONSUMER)

    assert emitted == {"ok", "degraded", "down", "not_applicable"}, emitted
    assert handled, "a consumer that branches on nothing would be a different shape"

    unhandled = emitted - handled
    assert unhandled == {"not_applicable"}, unhandled


def test_the_fallback_means_something_else_rather_than_failing():
    """THE HARM. A fallback that raised, or drew nothing, would be a visible bug. This one
    returns a radius of 0.0 at normal weight — a valid member of the same visual vocabulary
    as a genuine 0% — so "never measurable" and "completely down" render identically."""
    tree = ast.parse(CONSUMER)
    returns = [n for n in ast.walk(tree) if isinstance(n, ast.Return)]
    fallback = returns[-1]

    assert isinstance(fallback.value, ast.Dict)
    rendered = {
        key.value: getattr(value, "value", None)
        for key, value in zip(fallback.value.keys, fallback.value.values)
        if isinstance(key, ast.Constant)
    }
    assert rendered["radius"] == 0.0, rendered
    assert (
        rendered["weight"] == "normal"
    ), "a distinct weight would at least LOOK different; the finding is that it does not"

    # And the same rendering is reachable from a real measurement, which is the point.
    down_branch = [n for n in returns if isinstance(n.value, ast.Dict) and n is not fallback]
    zero_radius = [
        n
        for n in down_branch
        if any(isinstance(v, ast.Constant) and v.value == 0.0 for v in n.value.values)
    ]
    assert zero_radius, (
        "a genuine 0% must be reachable too -- otherwise the fallback is distinguishable"
        " and the fixture is not the finding"
    )

    assert "raise" not in CONSUMER, "the fixture must not fail loudly -- that is the remedy"


def test_the_lane_is_registered_and_is_not_the_sibling_lane():
    lane = _lane()
    assert lane["seat"] == SEAT, lane["seat"]
    assert lane["eval"] == "tests/evals/" + Path(__file__).name
    # `.strip()` because a YAML `>` folded scalar keeps a trailing newline. The
    # question still has to END in one, which is the actual contract -- a lane whose
    # "question" is a statement is a description, not something a reviewer answers.
    assert lane["question"].strip().endswith("?"), lane["question"]

    data = yaml.safe_load(
        (REPO_ROOT / "canonical" / "review_lanes.yml").read_text(encoding="utf-8")
    )
    sibling = next(
        lane for lane in data["lanes"] if lane["id"] == "a-produced-value-with-no-reader"
    )
    assert sibling["eval"] != lane["eval"], "two lanes may not share one fixture"
    assert sibling["question"] != lane["question"], (
        "an absent consumer and a wrong one are different questions with different"
        " remedies -- one lane answering both is how a lane stops being falsifiable"
    )
