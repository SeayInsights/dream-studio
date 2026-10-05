"""`core.gates.review_dimension_coverage` -- the 15-dimension visibility report.

`canonical/review_lanes.yml` holds 26 real lanes under 10 seats, each one earned by a
real defect a reviewer found once -- which means whole domains of review (performance,
API versioning, licensing, accessibility as its own seat, mobile) have no lane at all and
no way for an operator to see that except by reading all 26 by hand. This module declares
the 10 covered seats plus those 5 named gaps and reports lane counts per dimension,
without inventing a single lane to fill any gap.

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


def _real_lanes() -> list[dict]:
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    return [lane for lane in data["lanes"] if isinstance(lane, dict)]


# ── the 10 covered seats, counted live against the current registry ────────────────────


def test_declared_dimensions_are_exactly_fifteen():
    assert len(coverage.ALL_DIMENSIONS) == 15
    assert len(coverage.COVERED_DIMENSIONS) == 10
    assert len(coverage.GAP_DIMENSIONS) == 5
    # No overlap: a dimension is either a real seat or a named gap, never both.
    assert set(coverage.COVERED_DIMENSIONS).isdisjoint(coverage.GAP_DIMENSIONS)


def test_every_covered_dimension_shows_its_real_lane_count():
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
        assert row["covered"] is True
        assert row["lane_count"] == expected[seat_name]
        assert row["lane_count"] > 0
        assert len(row["lane_ids"]) == row["lane_count"]

    # And nothing in the live registry claims a seat this module has never heard of --
    # the same fact `test_declared_seats_reconcile_with_the_live_registry` checks via
    # reconcile(), asserted here directly against the report shape.
    assert set(expected) <= set(coverage.COVERED_DIMENSIONS)


def test_total_lane_count_across_covered_dimensions_matches_the_registry():
    lanes = _real_lanes()
    report = coverage.coverage_report(lanes=lanes)
    total_reported = sum(row["lane_count"] for row in report if row["covered"])
    assert total_reported == len(lanes)


# ── the 5 gap dimensions report zero, by name ───────────────────────────────────────────


def test_every_gap_dimension_reports_zero_lanes_by_name():
    report = {row["dimension"]: row for row in coverage.coverage_report()}
    for gap_name in coverage.GAP_DIMENSIONS:
        assert gap_name in report, f"{gap_name!r} must appear in the output even at zero"
        row = report[gap_name]
        assert row["covered"] is False
        assert row["lane_count"] == 0
        assert row["lane_ids"] == []


def test_gap_dimensions_are_genuinely_absent_from_the_registry_text():
    """Not just absent from COVERED_DIMENSIONS -- absent from the registry's own prose,
    so a gap row is a real gap and not an artifact of this module's own naming choice."""
    text = REGISTRY.read_text(encoding="utf-8").lower()
    for needle in ("performance", "licens", "mobile"):
        assert needle not in text, (
            f"{needle!r} appears in the registry; this gap may have been closed by a"
            " real lane and GAP_DIMENSIONS needs revisiting"
        )


# ── the drift check ──────────────────────────────────────────────────────────────────


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
    fake_lanes = [
        {"id": "x", "seat": "Access and reach"},
        {"id": "y", "seat": "Chair and verdict owner"},
    ]
    assert coverage.reconcile(lanes=fake_lanes) == []


def test_reconcile_result_feeds_run_status():
    """`run()` surfaces drift as a failing status, so a caller reading only `status` still
    learns the declaration has drifted -- the same shape `review_lane_registry.run()`
    already uses for its own pass/fail."""
    result = coverage.run()
    assert result["status"] == "pass"
    assert result["drift"] == []


# ── render() is readable, and names the gaps rather than omitting them ─────────────────


def test_render_names_every_gap_dimension_explicitly():
    rendered = coverage.render(coverage.run())
    for gap_name in coverage.GAP_DIMENSIONS:
        assert gap_name in rendered, f"{gap_name!r} must be a visible line, not silence"
        assert f"{gap_name}" in rendered
    for seat_name in coverage.COVERED_DIMENSIONS:
        assert seat_name in rendered


def test_render_reports_gap_lane_count_as_zero_in_text():
    rendered = coverage.render(coverage.run())
    lines = {line.strip() for line in rendered.splitlines()}
    for gap_name in coverage.GAP_DIMENSIONS:
        assert any(
            line.startswith(gap_name) and "0 lane(s)" in line for line in lines
        ), f"no visible '0 lane(s)' row for {gap_name!r}"
