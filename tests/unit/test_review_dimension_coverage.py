"""`core.gates.review_dimension_coverage` -- the 15-dimension visibility report.

`canonical/review_lanes.yml` holds 26 real lanes under 10 seats, each one earned by a
real defect a reviewer found once -- which means whole domains of review (performance,
API versioning, licensing, accessibility, mobile) have no SEAT of their own, and no way
for an operator to see that except by reading all 26 by hand. This module declares the
10 seated dimensions plus those 5 unseated ones and reports lane counts per dimension,
without inventing a single lane to fill any genuine gap.

A SEAT NAME IS NOT THE ONLY WAY A DIMENSION CAN BE COVERED. The first version of this
report grouped purely by seat and printed "Accessibility: 0" even though a real lane
(`accessibility`, filed under the unrelated "Interface conformance" seat) already asks
almost exactly that dimension's question -- a false claim, caught in review. These tests
lock in the fix: the lane-override mechanism (`LANE_SATISFIES_GAP`) that lets a dimension
be covered by a specific, hand-confirmed lane id even with no seat of its own, the
rejection of three near-miss candidates for "API versioning" and one for "Licensing"
(each cites a relevant STANDARD without the lane's actual QUESTION being about the
dimension), and the two genuinely empty dimensions (performance, mobile).

These tests compute the real registry's seat/lane shape live rather than asserting a
hardcoded expected count, per the operator's standing instruction to verify against
ground truth rather than a remembered number.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from core.gates import review_dimension_coverage as coverage

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY = REPO_ROOT / "canonical" / "review_lanes.yml"

#: The one gap dimension with a real lane-override today. Separated out everywhere these
#: tests iterate GAP_DIMENSIONS so a genuine 0-lane assertion is never silently applied to
#: the one dimension that is not actually 0 -- the exact bug this file exists to prevent.
_GENUINE_GAPS = tuple(d for d in coverage.GAP_DIMENSIONS if d != "Accessibility")


def _real_lanes() -> list[dict]:
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    return [lane for lane in data["lanes"] if isinstance(lane, dict)]


# ── the 10 seated dimensions, counted live against the current registry ────────────────


def test_declared_dimensions_are_exactly_fifteen():
    assert len(coverage.ALL_DIMENSIONS) == 15
    assert len(coverage.COVERED_DIMENSIONS) == 10
    assert len(coverage.GAP_DIMENSIONS) == 5
    # No overlap: a dimension is either a real seat or an unseated one, never both.
    assert set(coverage.COVERED_DIMENSIONS).isdisjoint(coverage.GAP_DIMENSIONS)
    assert _GENUINE_GAPS == ("Performance", "API versioning", "Licensing", "Mobile")


def test_every_seated_dimension_shows_its_real_lane_count():
    """Counted live off the registry on disk, not a number typed into this test."""
    lanes = _real_lanes()
    expected: dict[str, int] = {}
    for lane in lanes:
        seat = str(lane.get("seat", "")).strip()
        if seat:
            expected[seat] = expected.get(seat, 0) + 1

    report = {row["dimension"]: row for row in coverage.coverage_report(lanes=lanes)}

    for seat_name in coverage.COVERED_DIMENSIONS:
        assert seat_name in expected, (
            f"{seat_name!r} is declared covered but the live registry holds no lane"
            " under that seat at all"
        )
        row = report[seat_name]
        assert row["dedicated_seat"] is True
        assert row["match_kind"] == "seat"
        assert row["covered"] is True
        assert row["lane_count"] == expected[seat_name]
        assert row["lane_count"] > 0
        assert len(row["lane_ids"]) == row["lane_count"]

    # And nothing in the live registry claims a seat this module has never heard of --
    # the same fact `test_declared_seats_reconcile_with_the_live_registry` checks via
    # reconcile(), asserted here directly against the report shape.
    assert set(expected) <= set(coverage.COVERED_DIMENSIONS)


def test_total_lane_count_across_dedicated_seats_matches_the_registry():
    """Seat-matched rows partition the real lanes exactly once each. Lane-override rows
    (today: Accessibility) deliberately RE-COUNT a lane already counted under its real
    seat, so this invariant holds only for `dedicated_seat` rows -- see
    `test_lane_override_rows_recount_an_already_seated_lane_not_a_phantom_one` for the
    override rows' own invariant."""
    lanes = _real_lanes()
    report = coverage.coverage_report(lanes=lanes)
    total_dedicated = sum(row["lane_count"] for row in report if row["dedicated_seat"])
    assert total_dedicated == len(lanes)


def test_lane_override_rows_recount_an_already_seated_lane_not_a_phantom_one():
    """No lane-override row may point at a lane id that is not ALSO a real lane under some
    dedicated seat -- an override re-points at an existing lane, it never invents one."""
    lanes = _real_lanes()
    report = coverage.coverage_report(lanes=lanes)
    seated_lane_ids = {
        lane_id for row in report if row["dedicated_seat"] for lane_id in row["lane_ids"]
    }
    overridden_rows = [row for row in report if row["match_kind"] == "lane_override"]
    assert overridden_rows, "expected at least one lane-override row (Accessibility) today"
    for row in overridden_rows:
        for lane_id in row["lane_ids"]:
            assert lane_id in seated_lane_ids, (
                f"{lane_id!r} is reported as lane-override coverage for"
                f" {row['dimension']!r} but is not a real lane under any dedicated seat"
                " -- an override must point at a real, already-seated lane, never invent"
                " one."
            )


# ── Accessibility: covered via lane override, not a dedicated seat ─────────────────────


def test_accessibility_is_covered_by_the_real_lane_not_reported_as_a_false_zero():
    """THE BUG THIS FILE WAS WRITTEN TO CATCH. A real lane (`accessibility`) already asks
    this dimension's question; a report grouping only by seat name printed 0 anyway. This
    pins the fix: the dimension reports real coverage, with the true fact (no dedicated
    seat) carried alongside it rather than erased."""
    lanes = _real_lanes()
    report = {row["dimension"]: row for row in coverage.coverage_report(lanes=lanes)}
    row = report["Accessibility"]
    assert row["covered"] is True
    assert row["match_kind"] == "lane_override"
    assert row["dedicated_seat"] is False
    assert row["lane_count"] == 1
    assert row["lane_ids"] == ["accessibility"]


def test_the_accessibility_override_lane_is_genuinely_about_accessibility():
    """Not a false positive from a name coincidence: the real lane's own question is
    checked, the same rigor applied below to REJECT the API-versioning/licensing
    near-misses."""
    lanes = _real_lanes()
    by_id = {lane["id"]: lane for lane in lanes}
    real_lane = by_id["accessibility"]
    assert "screen reader" in real_lane["question"].lower()
    assert real_lane["seat"] == "Interface conformance", (
        "if this ever changes to seat == 'Accessibility', LANE_SATISFIES_GAP's entry is"
        " stale: coverage_report() would then find it via the seat match first and the"
        " override would be dead weight -- reconcile()'s bad-target check would also"
        " start firing since 'Accessibility' would no longer be in GAP_DIMENSIONS."
    )


# ── the 4 genuine gaps: zero lanes, by name, not inferred ───────────────────────────────


def test_the_four_genuine_gap_dimensions_report_zero_lanes_by_name():
    report = {row["dimension"]: row for row in coverage.coverage_report()}
    for gap_name in _GENUINE_GAPS:
        assert gap_name in report, f"{gap_name!r} must appear in the output even at zero"
        row = report[gap_name]
        assert row["covered"] is False
        assert row["match_kind"] == "none"
        assert row["dedicated_seat"] is False
        assert row["lane_count"] == 0
        assert row["lane_ids"] == []


def test_performance_and_mobile_have_no_mention_anywhere_in_the_registry():
    """The cleanest two gaps: not even a standard cited in passing, unlike licensing and
    API versioning below."""
    text = REGISTRY.read_text(encoding="utf-8").lower()
    for needle in ("performance", "mobile"):
        assert needle not in text, (
            f"{needle!r} appears in the registry; this gap may have been closed by a real"
            " lane and GAP_DIMENSIONS/LANE_SATISFIES_GAP need revisiting"
        )


def test_licensing_near_miss_is_a_citation_not_real_coverage():
    """`docs-style-and-attribution` cites 'SPDX licence identifiers' as a standard, but its
    actual question is attribution/PII hygiene, not license compliance -- confirmed by
    reading the full lane, not inferred from the citation. Pinned here so a future change
    to that lane's content is forced to re-examine whether this still holds, and so nobody
    re-derives this same investigation from scratch."""
    lanes = _real_lanes()
    by_id = {lane["id"]: lane for lane in lanes}
    candidate = by_id["docs-style-and-attribution"]
    assert "SPDX licence identifiers" in candidate.get("standards", [])
    assert "licen" not in candidate["question"].lower()
    assert "licen" not in candidate["signature"].lower()
    assert "Licensing" not in coverage.LANE_SATISFIES_GAP

    report = {row["dimension"]: row for row in coverage.coverage_report(lanes=lanes)}
    assert report["Licensing"]["covered"] is False
    assert report["Licensing"]["lane_count"] == 0


def test_api_versioning_near_misses_are_citations_not_real_coverage():
    """Three candidates cite Semantic Versioning or an API-surface standard; none of their
    actual QUESTIONS is about API versioning (release/package versioning, ADR mechanism
    completeness, and change disclosure, respectively -- each a different concern)."""
    lanes = _real_lanes()
    by_id = {lane["id"]: lane for lane in lanes}
    for lane_id in (
        "release-and-version-model",
        "a-contract-that-names-one-of-two-mechanisms",
        "an-unenumerated-behaviour-change",
    ):
        assert lane_id in by_id, f"{lane_id!r} expected in the live registry"
        question = by_id[lane_id]["question"].lower()
        assert "api version" not in question
        assert "versioning" not in question
    assert "API versioning" not in coverage.LANE_SATISFIES_GAP

    report = {row["dimension"]: row for row in coverage.coverage_report(lanes=lanes)}
    assert report["API versioning"]["covered"] is False
    assert report["API versioning"]["lane_count"] == 0


# ── the generic override mechanism, independent of today's specific registry data ──────


def test_a_lane_under_an_unrelated_seat_is_not_invisible_to_the_coverage_report():
    """The MECHANISM, proven without depending on the real registry's current shape --
    this is what the Accessibility fix above actually relies on. A lane whose content
    addresses a gap dimension must be found via an explicit override even though its seat
    carries a completely unrelated name."""
    fake_lanes = [
        {"id": "a-throughput-budget", "seat": "Totally Unrelated Seat"},
        {"id": "another-lane", "seat": "Also Unrelated"},
    ]
    fake_overrides = {"Performance": ("a-throughput-budget",)}
    report = {
        row["dimension"]: row
        for row in coverage.coverage_report(lanes=fake_lanes, overrides=fake_overrides)
    }
    perf = report["Performance"]
    assert perf["covered"] is True
    assert perf["match_kind"] == "lane_override"
    assert perf["dedicated_seat"] is False
    assert perf["lane_count"] == 1
    assert perf["lane_ids"] == ["a-throughput-budget"]
    # A dimension with no override declared, and no seat, is still correctly a gap.
    assert report["Mobile"]["covered"] is False
    assert report["Mobile"]["lane_count"] == 0


def test_a_seat_match_wins_over_an_override_for_the_same_dimension():
    """If a dimension ever gained a real seat of its own, the seat match must take over --
    an override is a fallback for when no seat exists, never a second, competing source of
    truth once one does."""
    fake_lanes = [{"id": "x", "seat": "Performance"}, {"id": "y", "seat": "Elsewhere"}]
    fake_overrides = {"Performance": ("y",)}
    report = {
        row["dimension"]: row
        for row in coverage.coverage_report(lanes=fake_lanes, overrides=fake_overrides)
    }
    assert report["Performance"]["match_kind"] == "seat"
    assert report["Performance"]["lane_ids"] == ["x"]


def test_a_stale_override_lane_id_disappears_from_the_report_but_is_caught_by_reconcile():
    fake_lanes = [{"id": "a-real-one", "seat": "Access and reach"}]
    fake_overrides = {"Performance": ("a-lane-that-does-not-exist",)}

    report = {
        row["dimension"]: row
        for row in coverage.coverage_report(lanes=fake_lanes, overrides=fake_overrides)
    }
    assert report["Performance"]["covered"] is False
    assert report["Performance"]["lane_count"] == 0

    errors = coverage.reconcile(lanes=fake_lanes, overrides=fake_overrides)
    assert errors, "a stale override lane id must be caught as drift, not silently dropped"
    assert any("a-lane-that-does-not-exist" in e for e in errors)


def test_an_override_targeting_an_already_seated_dimension_is_caught():
    fake_lanes = [{"id": "a-real-one", "seat": "Access and reach"}]
    fake_overrides = {"Access and reach": ("a-real-one",)}
    errors = coverage.reconcile(lanes=fake_lanes, overrides=fake_overrides)
    assert errors
    assert any("Access and reach" in e and "GAP_DIMENSIONS" in e for e in errors)


def test_todays_real_override_table_reconciles_clean():
    assert coverage.reconcile() == []


# ── the drift check on seat declarations ────────────────────────────────────────────────


def test_declared_seats_reconcile_with_the_live_registry():
    """The real registry's seat set must be a subset of COVERED_DIMENSIONS today. If this
    ever fails, a seat was added to canonical/review_lanes.yml (via scripts/seat_lanes_
    data.py's SEAT_MERGES) without updating COVERED_DIMENSIONS here."""
    assert coverage.reconcile() == []
    assert coverage.registry_seats() <= set(coverage.COVERED_DIMENSIONS)


def test_an_unknown_seat_is_caught_not_silently_ignored():
    """Simulated drift, via an injected lane list -- never by editing the real registry.
    A lane claiming a seat outside the declared set must be reported, not waved through."""
    fake_lanes = [
        {"id": "a-real-one", "seat": "Access and reach"},
        {"id": "a-new-one", "seat": "Performance budget steward"},
    ]
    errors = coverage.reconcile(lanes=fake_lanes)
    assert errors, "an unknown seat must be caught, not silently reconciled"
    assert any("Performance budget steward" in e for e in errors)
    assert any("COVERED_DIMENSIONS" in e for e in errors)


def test_an_entirely_known_lane_set_reconciles_clean():
    """Isolates the SEAT check from the (default) override check: this fake lane set is
    deliberately missing an `accessibility` lane, which would otherwise also trip the
    stale-override check this same module runs by default -- `overrides={}` scopes this
    test to the seat-reconciliation behavior it names."""
    fake_lanes = [
        {"id": "x", "seat": "Access and reach"},
        {"id": "y", "seat": "Chair and verdict owner"},
    ]
    assert coverage.reconcile(lanes=fake_lanes, overrides={}) == []


def test_reconcile_result_feeds_run_status():
    """`run()` surfaces drift as a failing status, so a caller reading only `status` still
    learns the declaration has drifted -- the same shape `review_lane_registry.run()`
    already uses for its own pass/fail."""
    result = coverage.run()
    assert result["status"] == "pass"
    assert result["drift"] == []


# ── render() is readable, and names the gaps (and the real override) rather than
# omitting or misreporting either ─────────────────────────────────────────────────────


def test_render_names_every_dimension_explicitly():
    rendered = coverage.render(coverage.run())
    for gap_name in coverage.GAP_DIMENSIONS:
        assert gap_name in rendered, f"{gap_name!r} must be a visible line, not silence"
    for seat_name in coverage.COVERED_DIMENSIONS:
        assert seat_name in rendered


def test_render_reports_the_four_genuine_gaps_as_zero_lanes_in_text():
    rendered = coverage.render(coverage.run())
    lines = {line.strip() for line in rendered.splitlines()}
    for gap_name in _GENUINE_GAPS:
        assert any(
            line.startswith(gap_name) and "0 lane(s)" in line for line in lines
        ), f"no visible '0 lane(s)' row for {gap_name!r}"


def test_render_reports_accessibility_as_one_lane_not_zero():
    """THE REGRESSION GUARD. Before the fix, this exact assertion would have found
    'Accessibility ... 0 lane(s)' instead -- a wrong claim printed to every operator who
    ran the command."""
    rendered = coverage.render(coverage.run())
    lines = {line.strip() for line in rendered.splitlines()}
    assert any(
        line.startswith("Accessibility") and "1 lane(s)" in line for line in lines
    ), "Accessibility must show its real 1-lane coverage, not a false 0"
    assert not any(line.startswith("Accessibility") and "0 lane(s)" in line for line in lines)
    assert "accessibility" in rendered  # the lane id itself, named
    assert "no dedicated seat" in rendered  # the honest caveat, not hidden either
