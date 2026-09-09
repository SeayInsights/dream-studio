"""Review lane ``an-unenumerated-behaviour-change`` — the Herald, gw#858.

THE FINDING. A second ack now raises instead of returning 200, and the consumer is the local
UI. The change was real and the PR body enumerated everything except that. Nobody
reading the body would know a caller's behaviour changed.

WHY THIS IS AN EVAL RATHER THAN A NEW GATE. The "must be written down" half already exists:
`core/gates/evidence_backed_output.py` audits what a push actually publishes -- the commit
messages of the commits being pushed and the lines added to CHANGELOG.md. Standing up a
second gate to audit the same documents would be two mechanisms for one rule, which is how
they drift and the weaker one becomes the policy.

What is missing is the DIFF side: recognising that a 200 became a raise. That half is graded
for now because "what a caller sees differently" is not decidable from a textual diff in
general -- a status constant can move, a decorator can translate exceptions, a return type
can widen without any literal changing. So this eval pins the fixture and the shape, and the
work order carries the task to extend the existing gate rather than add one.

WHAT THIS TEST CAN HONESTLY ASSERT: that the fixture is a genuine instance -- an existing
path that returned a status now raises -- and that the accompanying message does not mention
it. Not that a grader catches it; stubbing a grader would only test the stub.
"""

from __future__ import annotations

import ast
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

LANE_ID = "an-unenumerated-behaviour-change"

#: BEFORE: a second ack is idempotent and answers 200.
BEFORE = """
def acknowledge(session_id, store):
    if store.already_acked(session_id):
        return Response(status=200, body="already acknowledged")
    store.ack(session_id)
    return Response(status=200, body="acknowledged")
"""

#: AFTER: the same path now raises. Every caller that relied on the 200 -- here, the local
#: UI -- sees something new.
AFTER = """
def acknowledge(session_id, store):
    if store.already_acked(session_id):
        raise DuplicateAcknowledgement(session_id)
    store.ack(session_id)
    return Response(status=200, body="acknowledged")
"""

#: The message that shipped with it. Accurate about what it mentions, silent about the one
#: thing a caller would need to know.
MESSAGE = """fix(gateway): make the ack path idempotent under retry

Adds the per-card retry and shares the lock budget. Closes #795; the residual is declared
and tracked as #238.
"""


def _raises_on_existing_path(before: str, after: str, function: str) -> bool:
    """True when a path that used to return now raises, in the same function."""

    def _shape(source: str) -> tuple[int, int]:
        tree = ast.parse(source)
        target = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == function
        )
        returns = sum(1 for node in ast.walk(target) if isinstance(node, ast.Return))
        raises = sum(1 for node in ast.walk(target) if isinstance(node, ast.Raise))
        return returns, raises

    before_returns, before_raises = _shape(before)
    after_returns, after_raises = _shape(after)
    return after_raises > before_raises and after_returns < before_returns


def test_the_fixture_is_a_genuine_behaviour_change():
    """Asserted structurally, not by reading the prose: a path that returned now raises.

    Both halves matter. More raises alone could be a new error path added beside the old
    success one, which changes nothing for an existing caller. Fewer returns AND more
    raises is a path that used to answer and now throws.
    """
    assert _raises_on_existing_path(
        BEFORE, AFTER, "acknowledge"
    ), "the fixture does not exhibit a return becoming a raise"


def test_the_accompanying_message_does_not_mention_it():
    """The other half of the finding, and the reason it is a review lane at all.

    The message is not lazy -- it names the retry, the lock budget, the issue it closes and
    the residual it leaves. It is accurate about everything except the one thing a caller
    would need to know. A fixture whose message said nothing at all would be a much easier
    problem than the real one.
    """
    lowered = MESSAGE.lower()
    assert (
        "retry" in lowered and "#238" in MESSAGE
    ), "the fixture message must be otherwise thorough"
    # The tells a caller would need. An audit noted the first version carried an
    # `or tell == "idempotent"` clause that no loop value could ever reach -- inert rather
    # than disabling, and confusing, so it is gone.
    for tell in ("raise", "raises", "200", "status", "duplicate"):
        assert (
            tell not in lowered
        ), f"the fixture message mentions {tell!r}, so it does not exhibit the omission"


def test_the_existing_gate_is_the_one_to_extend():
    """Names the mechanism rather than duplicating it.

    `evidence_backed_output` already audits commit messages and added CHANGELOG lines. Two
    gates auditing the same documents would drift, and the weaker one would become the
    policy -- which is the coupling defect this session already fixed once in
    `scan_for_patterns`.
    """
    gate = REPO_ROOT / "core" / "gates" / "evidence_backed_output.py"
    assert gate.is_file(), "the gate this lane extends is missing"


def test_the_lane_is_registered_as_a_graded_one():
    lanes = yaml.safe_load(
        (REPO_ROOT / "canonical" / "review_lanes.yml").read_text(encoding="utf-8")
    )["lanes"]
    lane = next((entry for entry in lanes if entry.get("id") == LANE_ID), None)

    assert lane is not None, f"{LANE_ID} is not registered"
    assert lane.get("eval") == "tests/evals/test_review_lane_behaviour_change_enumerated.py"
    assert "evidence-backed-output" in str(
        lane.get("measurement")
    ), "the lane must name the existing gate it extends, or someone will build a second one"
