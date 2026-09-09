"""Convene the round table over a change set, before it is pushed.

WHY THIS EXISTS. `canonical/review_lanes.yml` holds the questions a review is obliged to
ask, and `review_lane_registry` proves each one is answerable — but proving a lane is
answerable is not asking it. Three of the six lanes are decided by a detector that the
pre-push chain already runs; the other three are decided by JUDGMENT, and nothing surfaced
them at the moment a reviewer needed them. A registry nobody can convene is half a
mechanism.

So this prints the table: it RUNS the detector lanes and reports what they found, and it
puts the graded and declared lanes in front of the reviewer as questions to answer against
the diff. Operator instruction, 2026-09-09: "use the round table to review anything before
it is pushed."

NOT A GATE, on purpose. The detector lanes are already blocking gates in
`canonical/workflows/pre-push.yaml`; adding a second caller that fails the same way would be
two mechanisms for one rule, which is how they drift and the weaker one becomes the policy.
This is the review surface, and its exit code reflects only whether the detectors it ran
could be run and came back clean.

IT CANNOT ANSWER THE GRADED LANES, and does not pretend to. It names them, asks their
question, and says which fixture teaches the shape. A reviewer who skips them has skipped
them visibly, which is the whole difference from a question that lived in someone's head.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path
from time import monotonic

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

REGISTRY = REPO_ROOT / "canonical" / "review_lanes.yml"

#: Wide enough for the longest seat, so the table reads as a table.
_SEAT_WIDTH = 14

#: Total wall clock the table may spend running detectors. Each is separately bounded at
#: 600s, and a per-item bound times a count is the very shape the Machinist watches for.
_TABLE_BUDGET_S = 900.0


def _lanes() -> list[dict]:
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    return [lane for lane in (data or {}).get("lanes", []) if isinstance(lane, dict)]


def _one_line(text: object) -> str:
    """A YAML folded block as a single line, for a report rather than a document."""
    return " ".join(str(text or "").split())


def _run_detector(command: str) -> tuple[bool, str]:
    """Run a lane's detector. Returns ``(clean, last_meaningful_line)``.

    A detector that cannot be RUN is reported as a failure, not skipped: silence from a
    check that never ran is indistinguishable from a check that found nothing, which is the
    fail-open shape `core/gates/fail_open_probe.py` exists for.
    """
    argv = shlex.split(command)
    if argv and argv[0] in ("py", "python", "python3"):
        argv[0] = sys.executable
    try:
        proc = subprocess.run(  # noqa: S603 - argv from the registry, shell=False
            argv,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"could not run ({type(exc).__name__}: {exc})"
    stream = (proc.stdout or "") + (proc.stderr or "")
    lines = [line.strip() for line in stream.splitlines() if line.strip()]
    return proc.returncode == 0, (lines[-1] if lines else "(no output)")


def convene(*, run_detectors: bool = True) -> dict:
    """The table's report for the current change set."""
    seats: list[dict] = []
    started = monotonic()
    for lane in _lanes():
        entry = {
            "seat": lane.get("seat", "?"),
            "lane": lane.get("id", "?"),
            "question": _one_line(lane.get("question")),
            "signature": _one_line(lane.get("signature")),
        }
        if "detector" in lane:
            entry["kind"] = "detector"
            entry["command"] = lane["detector"]
            if run_detectors:
                # AN AGGREGATE BUDGET, which is the Machinist's own question asked of this
                # module: each detector is bounded at 600s, and nothing bounded the total.
                # The registry is authored rather than data-driven, so the count is small
                # today -- but "small today" is what the lane it convenes exists to refuse.
                if monotonic() - started > _TABLE_BUDGET_S:
                    entry["clean"] = False
                    entry["detail"] = (
                        f"not run: the table passed its {_TABLE_BUDGET_S:.0f}s budget"
                        " before reaching this lane"
                    )
                else:
                    clean, detail = _run_detector(lane["detector"])
                    entry["clean"] = clean
                    entry["detail"] = detail
        elif "eval" in lane:
            entry["kind"] = "graded"
            entry["fixture"] = lane["eval"]
        else:
            entry["kind"] = "judgment"
            entry["why"] = _one_line(lane.get("why"))
        seats.append(entry)

    detectors = [s for s in seats if s["kind"] == "detector"]
    unclean = [s for s in detectors if not s.get("clean")]

    # THREE STATES, BECAUSE "NOTHING RAN" IS NOT "NOTHING FOUND".
    #
    # The Warden's own lane, applied to this module and found on its first convening:
    # `status` was "pass" whenever no detector was unclean, and with `run_detectors=False`
    # no detector is anything -- so a caller reading only `status` saw a pass from a run
    # that checked nothing. Two sites decided "is this clean", and this one consulted a
    # subset of what the other needed.
    if not run_detectors:
        status = "unchecked"
    elif unclean:
        status = "fail"
    else:
        status = "pass"

    return {
        "status": status,
        "lanes": seats,
        "detectors_run": len(detectors) if run_detectors else 0,
        "detectors_unclean": [s["lane"] for s in unclean] if run_detectors else [],
        "awaiting_judgment": [s["lane"] for s in seats if s["kind"] != "detector"],
    }


def _render(report: dict) -> str:
    lines: list[str] = ["", "THE ROUND TABLE", ""]

    for seat in report["lanes"]:
        if seat["kind"] != "detector":
            continue
        mark = "clean" if seat.get("clean") else "FOUND"
        lines.append(f"  [{mark:>5}] {seat['seat']:<{_SEAT_WIDTH}} {seat['lane']}")
        if not seat.get("clean"):
            lines.append(f"          {seat.get('detail', '')}")

    awaiting = [s for s in report["lanes"] if s["kind"] != "detector"]
    if awaiting:
        lines += ["", "  ASKED OF YOU — no detector can decide these:", ""]
        for seat in awaiting:
            lines.append(f"  {seat['seat']:<{_SEAT_WIDTH}} {seat['question']}")
            lines.append(f"  {'':<{_SEAT_WIDTH}} shape: {seat['signature']}")
            if seat["kind"] == "graded":
                lines.append(f"  {'':<{_SEAT_WIDTH}} fixture: {seat['fixture']}")
            else:
                lines.append(f"  {'':<{_SEAT_WIDTH}} unautomatable: {seat['why']}")
            lines.append("")

    if report["status"] == "unchecked":
        lines.append(
            "round-table: UNCHECKED - the detector lanes were not run, so this listing"
            f" answers nothing. {len(report['awaiting_judgment'])} lane(s) always need a"
            " person."
        )
    elif report["status"] == "pass":
        lines.append(
            f"round-table: {report['detectors_run']} detector lane(s) clean;"
            f" {len(report['awaiting_judgment'])} lane(s) need a person."
        )
    else:
        lines.append(
            f"round-table: {len(report['detectors_unclean'])} detector lane(s) found"
            f" something — {', '.join(report['detectors_unclean'])}."
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convene the review round table over the current change set."
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit the report as JSON instead of a table."
    )
    parser.add_argument(
        "--no-detectors",
        action="store_true",
        help="List the lanes without running the detectors (fast, and answers nothing).",
    )
    args = parser.parse_args(argv)

    report = convene(run_detectors=not args.no_detectors)
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else _render(report))
    # "unchecked" is a deliberate listing, not a failure -- but it is not a pass
    # either, and the report says so.
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
