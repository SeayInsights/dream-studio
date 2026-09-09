"""Review lane ``the-other-half-enforced-by-nothing`` — the Warden, plat#814.

WHY THIS IS AN EVAL AND NOT A GATE. A detector was prototyped and rejected on evidence.
Collecting every private predicate consulted in a boolean test across this repo found 421 of
them and 26 "subset-suspects", and reading the 26 showed they are arity differences
(``_table_exists(conn)`` beside ``_table_exists(conn, table)``), module aliases (``_yaml``),
and unrelated decisions in different files. A detector has no notion of "the same question",
which is the entire content of the finding. The number is recorded in
canonical/review_lanes.yml so the next person does not re-derive it.

SO WHAT CAN A TEST ASSERT? Not that a grader catches it -- stubbing a grader would only test
the stub. What it CAN assert, and does here, is that the fixture is a GENUINE instance of the
shape rather than a decorative one, and that the lane is actually registered. A judgment lane
whose fixture does not exhibit the defect is a lane that trains nobody.

THE FINDING, in the reviewer's own terms. A fix made delivery share ``_pat_rejected``
(revoked-or-expired) with the acceptance paths at app/auth.py:393+396 and :409. But those
also require ``_user_is_active``, and delivery consulted only the first. The code comment
claimed "delivery now shares that predicate, so the two cannot drift" -- true of one
predicate, false of the pair. The Herald's sentence, "treats expired PATs as deliverable even
though authentication rejects them", applied verbatim with `disabled` swapped for `expired`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

LANE_ID = "the-other-half-enforced-by-nothing"

#: THE FIXTURE IS THE FINDING. Two sites deciding one question -- is this credential
#: acceptable -- where acceptance requires two predicates and delivery consults one, under a
#: comment asserting the two cannot drift.
FIXTURE = """
def _pat_rejected(pat):
    return pat.revoked or pat.expired


def _user_is_active(user):
    return user.is_active and not user.disabled


def authentication_accepts(pat, user):
    # Both halves. A credential is acceptable only if the token is good AND the account is.
    if _pat_rejected(pat) or not _user_is_active(user):
        return False
    return True


def deliver_credential(pat, user, path):
    # Delivery now shares that predicate, so the two cannot drift.
    if _pat_rejected(pat):
        return False
    path.write_text(pat.secret)
    return True
"""


class _Pat:
    """A token that is neither revoked nor expired -- so `_pat_rejected` is False."""

    revoked = False
    expired = False
    secret = "s3cret-value"


class _Account:
    def __init__(self, *, active: bool) -> None:
        self.is_active = active
        self.disabled = not active


class _Sink:
    """Stands in for the destination, so "was a credential written" is observable."""

    def __init__(self) -> None:
        self.written: str | None = None

    def write_text(self, value: str) -> None:
        self.written = value


def _run_control(active: bool) -> dict[str, bool]:
    """Execute the FIXTURE against one account and report what each site decided.

    DERIVED, NOT TYPED OUT. An earlier version of this eval hand-wrote the control table and
    then asserted the literals equalled themselves -- an audit called it ceremony and was
    right: the fixture's functions were never executed, so the test verified nothing about
    the fixture. Running it is what makes this a reproduction.
    """
    namespace: dict[str, object] = {}
    # security-scan: FIXTURE is a module-level literal in this file, not input from
    # anywhere; executing it is how the control table is derived rather than typed out,
    # which is what an audit correctly called ceremony in the previous version.
    exec(compile(FIXTURE, "<lane-fixture>", "exec"), namespace)  # noqa: S102

    pat, account, sink = _Pat(), _Account(active=active), _Sink()
    return {
        "pat_rejected": bool(namespace["_pat_rejected"](pat)),
        "user_is_active": bool(namespace["_user_is_active"](account)),
        "auth_accepts": bool(namespace["authentication_accepts"](pat, account)),
        "delivered": bool(namespace["deliver_credential"](pat, account, sink))
        and sink.written is not None,
    }


def _predicates_in_decision(tree: ast.AST, function: str) -> set[str]:
    """Names of the predicate calls a function's decision consults."""
    target = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == function
    )
    found: set[str] = set()
    for node in ast.walk(target):
        if isinstance(node, (ast.If, ast.While)):
            for child in ast.walk(node.test):
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                    found.add(child.func.id)
    return found


def test_the_fixture_is_a_genuine_predicate_subset():
    """The lane's fixture must exhibit the defect, or it trains nobody.

    Asserts the asymmetry structurally rather than by reading the prose: acceptance consults
    two predicates, delivery consults one, and delivery's set is a strict subset of
    acceptance's. That is the whole shape.
    """
    tree = ast.parse(FIXTURE)
    accepts = _predicates_in_decision(tree, "authentication_accepts")
    delivers = _predicates_in_decision(tree, "deliver_credential")

    assert accepts == {"_pat_rejected", "_user_is_active"}, accepts
    assert delivers == {"_pat_rejected"}, delivers
    assert delivers < accepts, "the fixture does not exhibit a strict predicate subset"


def test_the_fixture_carries_the_claim_that_made_it_hard_to_see():
    """The comment is not decoration -- it is why the defect survived review.

    "The two cannot drift" is true of the predicate that was shared and false of the pair,
    and a reader who trusts it stops checking. A fixture without the claim would be an
    easier problem than the real one.
    """
    assert "cannot drift" in FIXTURE
    assert "shares that predicate" in FIXTURE


def test_the_control_shows_a_credential_delivered_that_auth_refuses():
    """THE REPRODUCTION, RUN. This is what made the finding blocker-class rather than a
    nitpick, and it is derived by executing the fixture rather than transcribed.

    A healthy account: every site agrees. A DISABLED account: the token is not rejected, the
    account is not active, authentication REFUSES -- and delivery writes the credential
    anyway. The Warden's sentence, and the Herald's before him, with `disabled` swapped for `expired`.
    """
    healthy = _run_control(active=True)
    assert healthy == {
        "pat_rejected": False,
        "user_is_active": True,
        "auth_accepts": True,
        "delivered": True,
    }, healthy

    disabled = _run_control(active=False)
    assert disabled["pat_rejected"] is False, "the token itself is fine; that is the trap"
    assert disabled["user_is_active"] is False, "the account is not active"
    assert disabled["auth_accepts"] is False, "authentication refuses it"
    assert disabled["delivered"] is True, (
        "and delivery wrote the credential anyway -- if this ever stops being true the"
        " fixture no longer reproduces plat#814"
    )


def test_the_lane_is_registered_as_a_graded_one():
    """A judgment lane that is not in the registry is not asked. The registry gate refuses
    a lane pointing at a missing eval; this is the other direction -- an eval with no lane."""
    lanes = yaml.safe_load(
        (REPO_ROOT / "canonical" / "review_lanes.yml").read_text(encoding="utf-8")
    )["lanes"]
    lane = next((entry for entry in lanes if entry.get("id") == LANE_ID), None)

    assert lane is not None, f"{LANE_ID} is not registered"
    assert lane.get("eval") == "tests/evals/test_review_lane_predicate_parity.py"
    assert "421" in str(lane.get("measurement")), (
        "the lane must carry the measurement that ruled out a detector, so the next person"
        " does not re-derive it"
    )
