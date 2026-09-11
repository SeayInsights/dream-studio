"""WO d0658106: a verdict that convened no lane is not a review.

THE DEFECT THIS EXISTS FOR. `canonical/review_lanes.yml` declared 29 seats and 30 lanes,
the `review-lane-registry` gate kept every one of them honest, and `convene()` had exactly
two callers -- its own CLI and its own test. Nothing in the close path convened the table,
and the verdict that gates close recorded scores, roots, rules and evidence layer while
naming no lens at all. A verdict produced with the whole bench and one produced with the
table never opened were byte-indistinguishable to `independent_review`.

Recording the seats on the verdict is provenance. Refusing a verdict that has none is what
makes it enforcement, and that refusal is what these tests hold.
"""

from __future__ import annotations

import json

import pytest

from core.work_orders import close_gates


@pytest.fixture
def gate(monkeypatch, tmp_path):
    """Run the REAL `independent_review` gate over a verdict we supply.

    Only the artifact read is stubbed -- the gate's own logic, including the envelope and
    staleness checks it applies before ours, runs unmodified. A test that reimplemented
    the predicate would pass while the gate did something else, which is the shape this
    module exists to refuse.
    """

    def run(verdict: dict, *, envelope: dict | None = None) -> tuple[bool, str]:
        monkeypatch.setattr(
            close_gates,
            "_artifact_with_envelope",
            lambda *a, **k: (
                json.dumps(verdict),
                envelope if envelope is not None else {"generator": "ds work-order verify"},
            ),
        )
        # Staleness is a separate concern with its own tests; neutralised so a failure
        # here is unambiguously about the table.
        monkeypatch.setattr(close_gates, "_provenance_staleness", lambda *a, **k: None)
        return close_gates.run_gate_check(
            "independent_review",
            planning_root=tmp_path,
            work_order_id="wo-under-test",
            project_id="proj",
            conn=None,
            db_path=tmp_path / "studio.db",
        )

    return run


_PASSING = {
    "passed": True,
    "certification_basis": "git_diff",
    "summary": "the work landed",
    "scores": {"composite": 0.9},
}


def test_a_verdict_that_convened_no_lane_is_refused(gate) -> None:
    """The core refusal. No `round_table` key at all: a pre-table verdict."""
    ok, reason = gate(dict(_PASSING))

    assert not ok, "a verdict naming no reviewer lens must not satisfy independent_review"
    assert "convened no lane" in reason
    assert "ds work-order verify" in reason, "a refusal must name the command that fixes it"


def test_a_round_table_section_with_no_seats_is_refused(gate) -> None:
    """Present but empty is the same absence, and is the shape a bug would produce.

    A convene() that raised and was swallowed, or a change set that narrowed to nothing,
    both write a section with an empty seat list. Accepting the key's PRESENCE rather than
    its CONTENT would make this gate satisfiable by writing `round_table: {}`.
    """
    ok, reason = gate({**_PASSING, "round_table": {"status": "pass", "seats": []}})

    assert not ok
    assert "convened no lane" in reason


def test_an_unavailable_table_says_why_it_was_unavailable(gate) -> None:
    """When convene() failed, the refusal must carry its reason, not a generic one.

    An operator who reads "convened no lane" and cannot tell whether the table is broken
    or the verdict is old will re-run verify forever.
    """
    ok, reason = gate(
        {
            **_PASSING,
            "round_table": {
                "status": "unavailable",
                "seats": [],
                "unavailable": "FileNotFoundError: registry missing",
            },
        }
    )

    assert not ok
    assert "FileNotFoundError: registry missing" in reason


def test_a_verdict_that_convened_lanes_passes_the_table_check(gate) -> None:
    """The positive case, so this gate is not a wall that refuses everything.

    Without this a `return False` in the new branch would satisfy every other test here.
    """
    ok, reason = gate(
        {
            **_PASSING,
            "round_table": {
                "status": "pass",
                "seats": [
                    {
                        "seat": "Event-substrate custodian",
                        "lane": "a-write-no-event-can-reconstruct",
                        "kind": "detector",
                        "clean": True,
                        "abstained": False,
                    }
                ],
            },
        }
    )

    assert ok, f"a verdict that convened a lane must clear the table check: {reason}"


def test_an_operator_attestation_is_exempt_and_still_closes(gate) -> None:
    """A person certifying work with no machine-traceable evidence convenes no table.

    There is no diff for a lane to be relevant to. Demanding the table here would either
    block `ds work-order attest` outright or invite convening a table nobody read -- so
    the exemption is deliberate, and this test is what stops the gate from silently
    breaking attestation the next time it is tightened.
    """
    ok, reason = gate(
        {
            "passed": True,
            "certification_basis": "operator_attested",
            "attestation": "design-only work, verified by hand",
            "summary": "attested",
        }
    )

    assert ok, f"operator attestation must remain closable: {reason}"


def test_a_FAILED_attestation_is_not_exempt(gate) -> None:
    """The exemption is "a person certified this", not "the basis string says attested".

    The first cut of this gate tested `certification_basis` alone while the sibling gate
    beside it tested basis AND `passed`. Two sites deciding one question, one consulting a
    subset of the other's predicates -- the exact lane. `verdict_is_operator_attested` is
    now the single definition, and this test fails if anyone re-splits it.
    """
    ok, reason = gate(
        {
            "passed": False,
            "certification_basis": "operator_attested",
            "summary": "attestation recorded against work that did not pass",
        }
    )

    assert not ok, "a failed attestation must not inherit the exemption a passing one gets"


def test_the_one_attestation_predicate_is_what_both_gates_read() -> None:
    """Held directly, so re-splitting the predicate fails here and not only by symptom."""
    f = close_gates.verdict_is_operator_attested

    assert f({"passed": True, "certification_basis": "operator_attested"})
    assert not f({"passed": False, "certification_basis": "operator_attested"})
    assert not f({"passed": True, "certification_basis": "git_diff"})
    assert not f({})


# ── The legacy-envelope fallback, entered rather than assumed ──────────────────
#
# `_envelope_absence_is_legacy` decides whether a MISSING provenance envelope is expected
# (the work order predates envelopes) or damning (it is hand-written). It had no test
# mentioning it anywhere, and the untested-fallback gate caught that the moment this module
# was touched -- a fallback runs only when the primary path is unavailable, which is the
# condition nobody develops in, so it is the code most likely to be wrong and least likely
# to be noticed.


class _FakeConn:
    """Answers the one query the helper makes, including by refusing to."""

    def __init__(self, created_at=None, raises=False):
        self._created_at = created_at
        self._raises = raises

    def execute(self, *_args, **_kwargs):
        if self._raises:
            raise RuntimeError("business_work_orders is not in this database")
        row = (self._created_at,) if self._created_at is not None else None

        class _Cursor:
            def fetchone(self_inner):
                return row

        return _Cursor()


def test_a_work_order_from_before_the_cutover_is_allowed_its_missing_envelope() -> None:
    """The fallback's reason for existing: envelopes did not exist yet."""
    assert close_gates._envelope_absence_is_legacy(
        _FakeConn(created_at="2026-08-18T12:00:00+00:00"), "wo-old"
    )


def test_a_work_order_from_after_the_cutover_is_not_excused() -> None:
    """The boundary in the other direction, without which the helper could return True
    unconditionally and every test above would still pass."""
    assert not close_gates._envelope_absence_is_legacy(
        _FakeConn(created_at="2026-08-20T12:00:00+00:00"), "wo-new"
    )


def test_the_cutover_day_itself_is_not_excused() -> None:
    """`<` not `<=`: a work order created ON the cutover day postdates it."""
    assert not close_gates._envelope_absence_is_legacy(
        _FakeConn(created_at=close_gates._PROVENANCE_CUTOVER + "T00:00:00+00:00"), "wo-edge"
    )


def test_an_unreadable_timestamp_fails_open_and_that_is_deliberate() -> None:
    """The branch nobody develops in, entered on purpose.

    Refusing to close a work order because its own timestamp is unreadable would be a
    worse failure than accepting one envelope-less artifact -- and the staleness check
    still applies to everything that DOES carry an envelope. Both unreadable shapes are
    driven: no row at all, and a query that raises.
    """
    assert close_gates._envelope_absence_is_legacy(_FakeConn(created_at=None), "wo-missing")
    assert close_gates._envelope_absence_is_legacy(_FakeConn(raises=True), "wo-no-table")


def test_the_envelope_requirement_consults_the_fallback() -> None:
    """The helper is reached from the gate, not merely defined beside it.

    A fallback with correct logic that nothing calls is the mechanism-with-no-caller
    shape; this drives `_envelope_required`, which is the only reason the helper exists.
    """
    old, new = _FakeConn("2026-08-18T00:00:00+00:00"), _FakeConn("2026-08-20T00:00:00+00:00")

    assert (
        close_gates._envelope_required(old, "wo-old", None, "review-verdict.json", "re-run verify")
        is None
    ), "a pre-cutover work order must not be refused for a missing envelope"

    refusal = close_gates._envelope_required(
        new, "wo-new", None, "review-verdict.json", "re-run verify"
    )
    assert refusal and "provenance envelope" in refusal
    assert "re-run verify" in refusal, "a refusal must carry the remedy it was handed"

    assert (
        close_gates._envelope_required(
            new, "wo-new", {"generator": "ds work-order verify"}, "review-verdict.json", "r"
        )
        is None
    ), "a present envelope short-circuits before the fallback is consulted at all"
