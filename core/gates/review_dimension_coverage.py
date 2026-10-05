"""Coverage report: every review dimension this system recognizes, named whether a real
lane asks about it or not.

WHY THIS EXISTS. `canonical/review_lanes.yml` holds 26 real lanes under 10 seats, and
every one of them exists because a specific reviewer found a specific defect that way
once -- the registry's own header says so. That makes its shape a record of review
HISTORY, not a designed map of what deserves review. Whole domains of software review
have no seat and no lane -- performance, API versioning, licensing, accessibility as its
own first-class concern, mobile-specific review -- and the gap is invisible by the same
mechanism that created it: nothing enumerates "Performance" beside "Access and reach" and
says 0. This module is that enumeration, read-only. It adds no lane, no detector, no
eval; it names the dimensions the registry does not ask about, so the gap is something
`ds review --coverage` states rather than something an operator finds only by reading
all 26 lanes by hand and counting what is missing.

NO LANES INVENTED, ON PURPOSE. A fabricated lane with no real precedent, no real
measurement and no real detector/eval would be worse than no lane at all for any of the
five gap dimensions below -- it is exactly the "prose dressed as a rule" failure mode
`canonical/review_lanes.yml`'s own header rejects. This module's only job is visibility.

THE FIFTEEN DECLARED DIMENSIONS. Ten are the seats `canonical/review_lanes.yml` convenes
today -- re-verified by reading the rendered registry (not assumed from an older count):
Access and reach, Boundary semantics, Chair and verdict owner, Claim integrity, Finding
integrity, Gate and test integrity, Interface conformance, Irreversible operations,
Publication and provenance, The receiver's view. Five are domains of defect confirmed
ABSENT from every lane's seat, scope, standards and prose by grepping both the registry
and its generator (`scripts/seat_lanes_data.py`) on 2026-10-05: performance, API
versioning, licensing, accessibility, mobile.

DECLARED HERE AS A LITERAL TUPLE, not derived from the registry at import time -- a
derived list could never disagree with the thing it was derived from, and the entire
point of this module is to notice when the registry's real seat set no longer matches
this declaration. `tests/unit/test_review_dimension_coverage.py::test_declared_seats_
reconcile_with_the_live_registry` is the mechanical check that the two still agree;
`reconcile()` below is the function it calls.

AN HONEST CAVEAT ON "ACCESSIBILITY". Grepping the generator for "accessibility" finds a
real lane -- id `accessibility`, seat "Interface conformance" -- asking almost exactly
this gap dimension's question ("can this be operated without a mouse, and does every
control have a name a screen reader will say?"). It is not literally true that nothing
anywhere asks about accessibility. What is missing is a DEDICATED SEAT: today it is one
of three unrelated concerns (design-system conformance, frontend behavior and payload,
accessibility) folded under one merged seat with one compiled reviewer, and the lane's
own `why` already admits its evidence is thin -- "71 records... essentially one reviewer
on one stack, which is itself the finding." This report counts dimensions by SEAT, which
is the level a lane is actually convened and dispatched at, so "Accessibility: 0" is
mechanically true of the seat namespace -- but letting that read as "nobody has ever
asked about accessibility" would be the exact kind of unfalsified claim this registry
exists to refuse, so it is stated here instead of hidden.

API versioning has a similar, much thinner near-miss: "Semantic Versioning 2.0.0 for API
surface" appears as a STANDARD cited by the (unrelated) Contract and protocol lane, and
plain "Semantic Versioning 2.0.0" is a standard on Release and version model -- neither
lane's QUESTION is about API versioning, both merely cite the spec in passing. Performance,
licensing and mobile have no mention anywhere in either file, thin near-miss or otherwise.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY = REPO_ROOT / "canonical" / "review_lanes.yml"

#: The 10 seats `canonical/review_lanes.yml` convenes today. A literal list, not derived
#: from the registry -- see this module's own docstring for why that is the point.
COVERED_DIMENSIONS: tuple[str, ...] = (
    "Access and reach",
    "Boundary semantics",
    "Chair and verdict owner",
    "Claim integrity",
    "Finding integrity",
    "Gate and test integrity",
    "Interface conformance",
    "Irreversible operations",
    "Publication and provenance",
    "The receiver's view",
)

#: Domains of defect confirmed absent from every lane's seat, scope, standards and prose.
#: Not a seat the registry convenes -- these have no lane, which is the gap this module
#: makes visible rather than filling with an invented one. See the module docstring's
#: caveat on "Accessibility" and "API versioning" before reading either as a literal zero.
GAP_DIMENSIONS: tuple[str, ...] = (
    "Performance",
    "API versioning",
    "Licensing",
    "Accessibility",
    "Mobile",
)

#: All fifteen, covered dimensions first, in the order a reader should see them.
ALL_DIMENSIONS: tuple[str, ...] = COVERED_DIMENSIONS + GAP_DIMENSIONS


def _load_lanes(registry: Path | None = None) -> list[dict[str, Any]]:
    import yaml

    path = registry or REGISTRY
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise FileNotFoundError(f"{path} could not be read ({exc})") from exc
    rows = data.get("lanes") if isinstance(data, dict) else data
    return [lane for lane in (rows or []) if isinstance(lane, dict)]


def registry_seats(
    *, lanes: list[dict[str, Any]] | None = None, registry: Path | None = None
) -> set[str]:
    """Every seat actually named by a real lane -- ground truth, not the declaration above.

    `lanes`, when given, is used in place of reading the file -- how
    `test_an_unknown_seat_is_caught_not_silently_ignored` simulates drift without editing
    the real registry: a lane list carrying a seat nothing declares exercises the same
    reconciliation this function and `reconcile()` run against the live file.
    """
    rows = lanes if lanes is not None else _load_lanes(registry)
    return {str(lane.get("seat", "")).strip() for lane in rows if lane.get("seat")}


def coverage_report(
    *, lanes: list[dict[str, Any]] | None = None, registry: Path | None = None
) -> list[dict[str, Any]]:
    """One row per declared dimension (all 15), covered or not, in `ALL_DIMENSIONS` order.

    Grouped by SEAT, not by lane id -- the level a lane is actually convened at (one seat
    compiles to one reviewer agent, `integrations/compiler/reviewers.py`). A gap dimension
    sharing a name with an existing LANE ID under a different seat (see "Accessibility" in
    the module docstring) still reports 0 lanes here, correctly: no seat in the registry is
    named after any of the five gap dimensions.
    """
    rows = lanes if lanes is not None else _load_lanes(registry)
    by_seat: dict[str, list[str]] = {}
    for lane in rows:
        seat = str(lane.get("seat", "")).strip()
        lane_id = str(lane.get("id", "")).strip()
        if seat and lane_id:
            by_seat.setdefault(seat, []).append(lane_id)

    report: list[dict[str, Any]] = []
    for dimension in ALL_DIMENSIONS:
        lane_ids = sorted(by_seat.get(dimension, []))
        report.append(
            {
                "dimension": dimension,
                "covered": dimension in COVERED_DIMENSIONS,
                "lane_count": len(lane_ids),
                "lane_ids": lane_ids,
            }
        )
    return report


def reconcile(
    *, lanes: list[dict[str, Any]] | None = None, registry: Path | None = None
) -> list[str]:
    """Drift between the declared dimension list and the registry's real seat set.

    Only checked in the direction that matters for a stale DECLARATION: every real lane's
    seat must map to one of the 10 names in `COVERED_DIMENSIONS`, or a seat added to
    `canonical/review_lanes.yml` (via `scripts/seat_lanes_data.py`'s `SEAT_MERGES`) without
    updating this module would make the coverage report silently wrong about what is
    covered -- the exact drift `review_lane_registry`'s own closed `SEATS` set exists to
    catch for seat membership, mirrored here for the coverage report's own declaration.

    Does not flag a declared dimension carrying zero real lanes as an error on its own --
    `coverage_report()` already reports that honestly as `lane_count: 0`, which is a
    correct answer, not drift, for one of the 5 gap dimensions. It would only become drift
    if a seat were later removed from the registry entirely while still being claimed as
    covered, and that case is out of scope for this reconciliation: the seat is simply
    reported with zero lanes, same as a gap dimension, until someone decides it should be
    reclassified.
    """
    real_seats = registry_seats(lanes=lanes, registry=registry)
    declared = set(COVERED_DIMENSIONS)
    unknown = sorted(real_seats - declared)
    if not unknown:
        return []
    return [
        "canonical/review_lanes.yml names seat(s) not declared in"
        " core.gates.review_dimension_coverage.COVERED_DIMENSIONS:"
        f" {unknown}. A seat added to the registry"
        " (scripts/seat_lanes_data.py's SEAT_MERGES) must also be declared here, or the"
        " coverage report silently stops matching reality."
    ]


def run(*, registry: Path | None = None) -> dict[str, Any]:
    """The report `ds review --coverage` prints, as data."""
    lanes = _load_lanes(registry)
    drift = reconcile(lanes=lanes)
    return {
        "status": "fail" if drift else "pass",
        "dimensions": coverage_report(lanes=lanes),
        "drift": drift,
    }


def render(result: dict[str, Any]) -> str:
    rows = result["dimensions"]
    width = max((len(row["dimension"]) for row in rows), default=0) + 2
    lines = ["REVIEW DIMENSION COVERAGE", ""]
    for row in rows:
        marker = "covered" if row["covered"] else "GAP"
        lines.append(f"  {row['dimension']:<{width}} {marker:<8} {row['lane_count']} lane(s)")
        if row["lane_ids"]:
            lines.append(f"  {'':<{width}} {'':<8} {', '.join(row['lane_ids'])}")
    covered_n = sum(1 for row in rows if row["covered"])
    gap_n = len(rows) - covered_n
    lines += [
        "",
        f"{covered_n} of {len(rows)} declared dimensions have a real lane backing them;"
        f" {gap_n} are named gaps with no lane fabricated to fill them.",
    ]
    if result.get("drift"):
        lines += ["", "DRIFT:"]
        lines += [f"  - {item}" for item in result["drift"]]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report review-dimension coverage: which of the 15 declared review"
        " dimensions have a real lane in canonical/review_lanes.yml, and which are named"
        " gaps with none."
    )
    parser.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    args = parser.parse_args(argv)
    result = run()
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else render(result))
    return 1 if result["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
