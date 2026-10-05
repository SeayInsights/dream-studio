"""Coverage report: every review dimension this system recognizes, named whether a real
lane asks about it or not.

WHY THIS EXISTS. `canonical/review_lanes.yml` holds 26 real lanes under 10 seats, and
every one of them exists because a specific reviewer found a specific defect that way
once -- the registry's own header says so. That makes its shape a record of review
HISTORY, not a designed map of what deserves review. Whole domains of software review
have no SEAT -- performance, API versioning, licensing, accessibility as a first-class
concern, mobile-specific review -- and the gap is invisible by the same mechanism that
created it: nothing enumerates "Performance" beside "Access and reach" and says so. This
module is that enumeration, read-only. It adds no lane, no detector, no eval; it names
the dimensions the registry has no SEAT for, and separately reports whether a real LANE
already covers one anyway, so the gap is something `ds review --coverage` states
accurately rather than something an operator either finds by reading all 26 lanes by
hand, or gets told a false zero about by a report that only looked at seat names.

NO LANES INVENTED, ON PURPOSE. A fabricated lane with no real precedent, no real
measurement and no real detector/eval would be worse than no lane at all for any of the
four genuinely-empty gap dimensions below -- it is exactly the "prose dressed as a rule"
failure mode `canonical/review_lanes.yml`'s own header rejects. This module's only job
is visibility, including visibility into coverage that already exists under an
unexpected name.

THE FIFTEEN DECLARED DIMENSIONS. Ten are the seats `canonical/review_lanes.yml` convenes
today -- re-verified by reading the rendered registry (not assumed from an older count):
Access and reach, Boundary semantics, Chair and verdict owner, Claim integrity, Finding
integrity, Gate and test integrity, Interface conformance, Irreversible operations,
Publication and provenance, The receiver's view. Five have no seat of their own:
performance, API versioning, licensing, accessibility, mobile.

DECLARED HERE AS A LITERAL TUPLE, not derived from the registry at import time -- a
derived list could never disagree with the thing it was derived from, and part of the
point of this module is to notice when the registry's real seat set no longer matches
this declaration. `tests/unit/test_review_dimension_coverage.py::test_declared_seats_
reconcile_with_the_live_registry` is the mechanical check that the two still agree;
`reconcile()` below is the function it calls.

A DIMENSION WITH NO SEAT CAN STILL HAVE A REAL LANE, filed under an unrelated seat for
that seat's own merge-history reasons rather than for the dimension's. Grouping only by
seat name would then print a false zero beside a lane that already asks the dimension's
real question -- found on this module's own first review: the `accessibility` lane
(seat "Interface conformance", filed there alongside design-system conformance and
frontend behavior/payload, none of which it is about) asks almost exactly the
Accessibility dimension's question and was reported as 0 anyway, which is a worse
failure than silence -- an explicit, wrong claim about coverage that exists. So
`LANE_SATISFIES_GAP` below is a second, narrower lookup: specific lane ids, read in full
and hand-confirmed to genuinely be ABOUT a gap dimension (not merely citing a standard
adjacent to it), checked after the seat lookup finds nothing. This is deliberately NOT a
keyword or fuzzy match against lane prose -- that would also credit a lane that cites a
standard in passing as if the standard were the lane's actual subject, which is exactly
the false-positive shape the rejected candidates documented on `LANE_SATISFIES_GAP`
below demonstrate. A dimension covered this way still has NO DEDICATED SEAT (no compiled
reviewer agent asks only about it; see `dedicated_seat` on each report row) -- that fact
is reported too, not collapsed into looking identical to a seat-backed dimension.
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

#: Dimensions with no seat of their own in `canonical/review_lanes.yml` -- not
#: necessarily zero real lanes (see `LANE_SATISFIES_GAP`), but zero DEDICATED ones.
GAP_DIMENSIONS: tuple[str, ...] = (
    "Performance",
    "API versioning",
    "Licensing",
    "Accessibility",
    "Mobile",
)

#: All fifteen, covered dimensions first, in the order a reader should see them.
ALL_DIMENSIONS: tuple[str, ...] = COVERED_DIMENSIONS + GAP_DIMENSIONS

#: A gap dimension's own topic can already be the live subject of a specific lane filed
#: under an unrelated seat. Declared lane id by lane id, only after reading the
#: candidate's actual `question`/`signature`/`precedent` in full -- never inferred from a
#: keyword hit against a lane's prose, which would also credit a passing citation. Every
#: entry (and every REJECTED candidate below) is `reconcile()`-checked against the live
#: registry so a renamed or removed lane id is caught as drift, not silently reverting to
#: a wrong zero with nobody noticing which direction it changed.
#:
#: ACCESSIBILITY -- COVERED. `accessibility` (seat "Interface conformance") asks "Can
#: this be operated without a mouse, and does every control have a name a screen reader
#: will say?" That is this dimension's actual subject, not a passing citation; declared
#: thin on purpose (the lane's own `why` already says the evidence is "71 records...
#: essentially one reviewer on one stack"), but thin coverage is still coverage, and
#: reporting it as a flat 0 would itself be the unfalsified claim this registry exists
#: to refuse.
#:
#: API VERSIONING -- NOT COVERED. Three candidates were read in full and rejected, not
#: merely absent from a keyword grep:
#:   - `release-and-version-model` (seat "Publication and provenance") cites "Semantic
#:     Versioning 2.0.0" and asks whether "the version this produces mean[s] what the
#:     ecosystem consuming it thinks it means" -- RELEASE/PACKAGE versioning (a git tag,
#:     a CFBundleShortVersionString, a CHANGELOG entry), a different question from API
#:     versioning (a URL or header version, a deprecation window, parallel old/new
#:     surfaces). A project could pass this lane's question perfectly -- every tag
#:     SemVer-correct -- with no API versioning scheme at all.
#:   - `a-contract-that-names-one-of-two-mechanisms` (seat "Claim integrity") cites
#:     "Semantic Versioning 2.0.0 for API surface" among FOUR standards (with OpenAPI,
#:     JSON Schema, RFC 9457), but its question is whether a decision record names every
#:     mechanism a claim depends on -- ADR completeness, not API versioning. The citation
#:     is a standard the seat is measured against in general, not this lane's subject.
#:   - `an-unenumerated-behaviour-change` (seat "Claim integrity") asks "what does a
#:     caller see differently after this change, and does the change say so" --
#:     genuinely about a caller-visible contract change, but about whether the change is
#:     DISCLOSED in the PR body, not whether the API is VERSIONED for it. Disclosure and
#:     versioning are different remedies for different failures.
#:
#: LICENSING -- NOT COVERED. `docs-style-and-attribution` (seat "The receiver's view")
#: cites "SPDX licence identifiers" among three standards, but its question is "does
#: anything shipping here carry a name, a path, or a trailer that should not leave this
#: machine" -- attribution and PII hygiene, never license compliance (dependency license
#: compatibility, a file's own SPDX header, a project's own LICENSE accuracy). Same
#: citation-is-not-subject shape as the API-versioning near-misses above.
#:
#: PERFORMANCE and MOBILE -- NOT COVERED, and not even a near-miss: zero mentions,
#: standard or otherwise, anywhere in the registry or its generator (grepped 2026-10-05,
#: multiple spellings/adjacent terms each: performance/latency/throughput/benchmark/
#: profiling; mobile/iOS/Android/responsive/viewport/touch target).
LANE_SATISFIES_GAP: dict[str, tuple[str, ...]] = {
    "Accessibility": ("accessibility",),
}


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
    *,
    lanes: list[dict[str, Any]] | None = None,
    registry: Path | None = None,
    overrides: dict[str, tuple[str, ...]] | None = None,
) -> list[dict[str, Any]]:
    """One row per declared dimension (all 15), in `ALL_DIMENSIONS` order.

    Two ways a dimension can be covered, checked in order, and both named on the row:

    1. SEAT MATCH -- the dimension's name is itself a seat in the registry; every lane
       filed under that seat counts (`match_kind: "seat"`, `dedicated_seat: True`). This
       is the level a lane is actually convened and dispatched at (one seat compiles to
       one reviewer agent, `integrations/compiler/reviewers.py`).
    2. LANE OVERRIDE -- the dimension has no seat, but `overrides` (default
       `LANE_SATISFIES_GAP`) names a specific lane id that is genuinely about it, filed
       under an unrelated seat (`match_kind: "lane_override"`, `dedicated_seat: False`).
       An overridden lane id that no longer exists in `lanes` is silently dropped here
       (falls through to `match_kind: "none"`) -- `reconcile()` is what reports that
       specific failure as drift rather than a quiet, undiagnosed zero.

    `covered` is `lane_count > 0` either way: a reader asking "is this dimension real
    coverage, or a fabricated zero" gets one honest boolean; `dedicated_seat` and
    `match_kind` are there for the reader who also wants to know whether that coverage
    comes with its own reviewer agent or only borrows one.
    """
    rows = lanes if lanes is not None else _load_lanes(registry)
    overrides = LANE_SATISFIES_GAP if overrides is None else overrides

    by_seat: dict[str, list[str]] = {}
    known_ids: set[str] = set()
    for lane in rows:
        seat = str(lane.get("seat", "")).strip()
        lane_id = str(lane.get("id", "")).strip()
        if lane_id:
            known_ids.add(lane_id)
        if seat and lane_id:
            by_seat.setdefault(seat, []).append(lane_id)

    report: list[dict[str, Any]] = []
    for dimension in ALL_DIMENSIONS:
        if dimension in by_seat:
            lane_ids = sorted(by_seat[dimension])
            match_kind = "seat"
        else:
            override_ids = sorted(lid for lid in overrides.get(dimension, ()) if lid in known_ids)
            lane_ids = override_ids
            match_kind = "lane_override" if override_ids else "none"
        report.append(
            {
                "dimension": dimension,
                "dedicated_seat": dimension in COVERED_DIMENSIONS,
                "covered": len(lane_ids) > 0,
                "match_kind": match_kind,
                "lane_count": len(lane_ids),
                "lane_ids": lane_ids,
            }
        )
    return report


def reconcile(
    *,
    lanes: list[dict[str, Any]] | None = None,
    registry: Path | None = None,
    overrides: dict[str, tuple[str, ...]] | None = None,
) -> list[str]:
    """Drift between what this module declares and what the registry actually holds.

    Three checks, each naming exactly what went stale:

    1. Every real lane's seat must map to one of the 10 names in `COVERED_DIMENSIONS`,
       or a seat added to `canonical/review_lanes.yml` (via `scripts/seat_lanes_data.py`'s
       `SEAT_MERGES`) without updating this module would make the coverage report
       silently wrong about what has a dedicated seat -- the exact drift
       `review_lane_registry`'s own closed `SEATS` set exists to catch for seat
       membership, mirrored here for this module's own declaration.
    2. Every `LANE_SATISFIES_GAP` lane id must still exist in the registry, or an
       override that used to point at a real lane (renamed, merged away, deleted) would
       silently stop covering anything and the dimension would revert to a 0 that reads
       exactly like an honest gap instead of a broken override nobody noticed.
    3. Every `LANE_SATISFIES_GAP` key must be one of `GAP_DIMENSIONS` -- an override on a
       dimension that already has a seat is redundant and almost certainly a copy-paste
       mistake naming the wrong dimension.

    Does not flag a declared dimension carrying zero real lanes as an error on its own --
    `coverage_report()` already reports that honestly as `lane_count: 0`, which is a
    correct answer for a genuine gap, not drift.
    """
    rows = lanes if lanes is not None else _load_lanes(registry)
    overrides = LANE_SATISFIES_GAP if overrides is None else overrides
    errors: list[str] = []

    real_seats = registry_seats(lanes=rows)
    unknown_seats = sorted(real_seats - set(COVERED_DIMENSIONS))
    if unknown_seats:
        errors.append(
            "canonical/review_lanes.yml names seat(s) not declared in"
            " core.gates.review_dimension_coverage.COVERED_DIMENSIONS:"
            f" {unknown_seats}. A seat added to the registry"
            " (scripts/seat_lanes_data.py's SEAT_MERGES) must also be declared here, or"
            " the coverage report silently stops matching reality."
        )

    bad_targets = sorted(set(overrides) - set(GAP_DIMENSIONS))
    if bad_targets:
        errors.append(
            f"LANE_SATISFIES_GAP declares override(s) for {bad_targets}, which"
            f" {'is' if len(bad_targets) == 1 else 'are'} not in GAP_DIMENSIONS -- an"
            " override only means something for a dimension with no seat of its own; a"
            " dimension already seat-covered needs no override and a target here is"
            " almost certainly the wrong dimension name."
        )

    known_ids = {str(lane.get("id", "")).strip() for lane in rows if lane.get("id")}
    for dimension, lane_ids in overrides.items():
        missing_ids = sorted(lid for lid in lane_ids if lid not in known_ids)
        if missing_ids:
            errors.append(
                f"LANE_SATISFIES_GAP[{dimension!r}] names lane id(s) {missing_ids} that"
                " do not exist in the registry -- the override has gone stale (renamed,"
                " merged, or removed) and would silently report 0 lanes again instead of"
                " surfacing as a problem."
            )
    return errors


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
        if row["match_kind"] == "seat":
            marker = "covered"
        elif row["match_kind"] == "lane_override":
            marker = "covered*"
        else:
            marker = "GAP"
        lines.append(f"  {row['dimension']:<{width}} {marker:<9} {row['lane_count']} lane(s)")
        if row["lane_ids"]:
            lines.append(f"  {'':<{width}} {'':<9} {', '.join(row['lane_ids'])}")

    covered_n = sum(1 for row in rows if row["covered"])
    dedicated_n = sum(1 for row in rows if row["dedicated_seat"])
    overridden_n = covered_n - dedicated_n
    gap_n = len(rows) - covered_n
    lines += [
        "",
        f"{covered_n} of {len(rows)} declared dimensions have a real lane backing them"
        f" ({dedicated_n} with a dedicated seat"
        + (f", {overridden_n} via a lane filed under an unrelated seat" if overridden_n else "")
        + f"); {gap_n} are named gaps with no lane fabricated to fill them.",
    ]

    overridden_rows = [row for row in rows if row["match_kind"] == "lane_override"]
    if overridden_rows:
        lines += ["", "* no dedicated seat -- covered by a lane filed under a different seat:"]
        for row in overridden_rows:
            lines.append(f"  {row['dimension']}: {', '.join(row['lane_ids'])}")

    if result.get("drift"):
        lines += ["", "DRIFT:"]
        lines += [f"  - {item}" for item in result["drift"]]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report review-dimension coverage: which of the 15 declared review"
        " dimensions have a real lane in canonical/review_lanes.yml (by dedicated seat or"
        " by an explicit lane-level override), and which are genuine gaps with none."
    )
    parser.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    args = parser.parse_args(argv)
    result = run()
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else render(result))
    return 1 if result["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
