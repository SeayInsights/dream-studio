"""Convene the round table over a change set, before it is pushed.

WHY THIS EXISTS. `canonical/review_lanes.yml` holds the questions a review is obliged to
ask, and `review_lane_registry` proves each one is answerable — but proving a lane is
answerable is not asking it. Some lanes are decided by a detector the pre-push chain
already runs; the rest are decided by JUDGMENT, and nothing surfaced those at the moment
a reviewer needed them. A registry nobody can convene is half a mechanism.

NO COUNT IS STATED HERE ON PURPOSE. This said "three of the six lanes" and was wrong
within a day of the registry growing — the Archivist's lane, on this module. The
registry is the count; a docstring restating it is a second source that can only drift.

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
from fnmatch import fnmatch
import sys
from pathlib import Path
from time import monotonic

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Kept for callers that import it. The registry is resolved from the TARGET root instead,
#: so another project can carry its own lanes -- see `registry_for`.
REGISTRY = REPO_ROOT / "canonical" / "review_lanes.yml"


#: Where a shipped install keeps the registry, relative to the plugin root.
_SHIPPED_REGISTRY = ("review", "review_lanes.yml")


def registry_for(repo_root: Path | None = None) -> Path:
    """Where the lanes live for the tree being reviewed.

    Another project reviewing itself should be asked ITS questions, not this repo's, so the
    registry travels with the tree rather than with the convener.

    TWO LAYOUTS, because the convener now ships. In a source checkout the registry is
    `canonical/review_lanes.yml`; in a plugin install it is `review/review_lanes.yml`
    beside the shipped convener. The source layout is preferred when both exist, so a
    developer working in the repo is always asked the repo's live questions rather than a
    stale copy inside `dist/`.
    """
    root = repo_root or REPO_ROOT
    canonical = root / "canonical" / "review_lanes.yml"
    if canonical.is_file():
        return canonical
    shipped = root.joinpath(*_SHIPPED_REGISTRY)
    if shipped.is_file():
        return shipped
    # Neither exists: return the canonical path so the error names the conventional home.
    return canonical


#: Floor for the seat column. The real width is DERIVED per render, see `_seat_width`.
_SEAT_WIDTH = 14


def _seat_width(report: dict) -> int:
    """Width of the seat column, measured from the seats actually being rendered.

    THE INTERPRETER'S SECOND LANE, FOUND ON THE CHANGE THAT ADDED THAT SEAT. This was
    `_SEAT_WIDTH = 14` under a comment reading "wide enough for the longest seat, so the
    table reads as a table" -- the intent stated in prose and enforced by nothing. Seating
    "The Interpreter" (15 characters) overflowed the column, shifting every question one
    space left, and nothing failed: a misaligned table still looks like a table, which is
    that lane's own signature -- the producer grew a vocabulary member and the far end
    rendered it wrong rather than refusing it.

    Derived, so the next seat cannot repeat it.
    """
    seats = [str(seat.get("seat", "")) for seat in report.get("lanes", [])]
    return max([_SEAT_WIDTH, *(len(seat) for seat in seats)])


#: Total wall clock the table may spend running detectors. Each is separately bounded at
#: 600s, and a per-item bound times a count is the very shape the Machinist watches for.
_TABLE_BUDGET_S = 900.0


def _lanes(repo_root: Path | None = None) -> list[dict]:
    registry = registry_for(repo_root)
    if not registry.is_file():
        raise FileNotFoundError(
            f"no review-lane registry at {registry}. A convening with no lanes is not a"
            " clean review -- it is a review that asked nothing, so this raises rather than"
            " reporting an empty table."
        )
    data = yaml.safe_load(registry.read_text(encoding="utf-8"))
    return [lane for lane in (data or {}).get("lanes", []) if isinstance(lane, dict)]


def _one_line(text: object) -> str:
    """A YAML folded block as a single line, for a report rather than a document."""
    return " ".join(str(text or "").split())


#: Prefix marking a detail as "this lane could not be checked" rather than "this lane found
#: something". Carried in the detail string so no call signature changes and every existing
#: caller keeps working; `convene` reads it to set the seat's state.
_UNRUNNABLE = "[unrunnable] "


def _module_missing(returncode: int, stream: str) -> bool:
    """Did the child fail because the detector is not installed?

    A missing module is Python exiting 1 with "No module named". Distinguishing it from a
    real finding is the whole point: in a skills-only install every detector is missing,
    and reporting four findings where there are none is the Interpreter's lane -- a value
    shown as another value's meaning.
    """
    lowered = stream.lower()
    return returncode != 0 and ("no module named" in lowered or "can't open file" in lowered)


def _run_detector(command: str, repo_root: Path | None = None) -> tuple[bool, str]:
    """Run a lane's detector. Returns ``(clean, last_meaningful_line)``.

    A detector that cannot be RUN is reported as a failure, not skipped: silence from a
    check that never ran is indistinguishable from a check that found nothing, which is the
    fail-open shape `core/gates/fail_open_probe.py` exists for.
    """
    argv = shlex.split(command)
    if argv and argv[0] in ("py", "python", "python3"):
        argv[0] = sys.executable

    # TELL THE DETECTOR WHICH TREE TO SCAN, but only when it is not this one -- a same-repo
    # convening is unchanged. A detector that does not accept the flag will exit non-zero on
    # an unrecognised argument, and that is reported as a lane that could not be pointed at
    # the target rather than as a clean lane. Dropping the flag and running anyway would
    # scan the convener's own install and call another project green.
    target = Path(repo_root) if repo_root else None
    retargeted = bool(target and target.resolve() != REPO_ROOT.resolve())
    if retargeted:
        argv += ["--repo-root", str(target)]
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
        return False, f"{_UNRUNNABLE}could not run ({type(exc).__name__}: {exc})"
    stream = (proc.stdout or "") + (proc.stderr or "")
    lines = [line.strip() for line in stream.splitlines() if line.strip()]
    if _module_missing(proc.returncode, stream):
        # NOT A FINDING. The detector is absent -- which is the normal state of a
        # skills-only install, where `core.gates` does not ship. Rendering it as FOUND
        # would report four defects where there are none.
        return False, (
            f"{_UNRUNNABLE}the detector module is not installed here, so this lane was not"
            " checked. A plugin install ships the registry and the convener; the detector"
            " packages live in the source repo."
        )
    if retargeted and _rejected_the_flag(stream):
        return False, (
            "could not be pointed at the target tree: this detector does not accept"
            " --repo-root, so running it would have scanned the convener's own install and"
            " reported that as this project's result. Parameterise the detector."
        )
    return proc.returncode == 0, (lines[-1] if lines else "(no output)")


def _rejected_the_flag(stream: str) -> bool:
    """Did the child refuse `--repo-root` rather than run and find something?

    argparse says "unrecognized arguments" and exits 2. Distinguishing that from a genuine
    finding matters: one is a defect in the lane and the other is a defect in the project,
    and reporting the first as the second sends someone hunting in the wrong tree.
    """
    lowered = stream.lower()
    return "unrecognized arguments" in lowered and "--repo-root" in lowered


def changed_paths(repo_root: Path | None = None) -> list[str]:
    """Repo-relative paths this change set touches, or [] when git cannot say.

    [] IS NOT "NOTHING CHANGED" -- it is "I could not tell", and the caller treats it as a
    reason to convene everything rather than nothing. A selector that silently narrows to
    zero would report a clean review of a tree it never looked at, which is the
    compared-nothing-reported-clean shape every lane here exists to refuse.
    """
    root = repo_root or REPO_ROOT
    paths: set[str] = set()
    for args in (
        ["git", "diff", "--name-only", "HEAD"],
        ["git", "diff", "--name-only", "--cached"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        try:
            proc = subprocess.run(
                args,
                cwd=str(root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        paths.update(line.strip() for line in (proc.stdout or "").splitlines() if line.strip())
    return sorted(paths)


def lane_is_relevant(lane: dict, paths: list[str]) -> bool:
    """Does this lane's scope match anything in the change set?

    A lane with NO scope ALWAYS fires. Absence means "always relevant", not "forgotten" --
    the cost of wrongly hiding a lane is a defect nobody was asked about, while the cost of
    wrongly showing one is a line of output, so the default leans toward showing.
    """
    patterns = lane.get("scope") or []
    if not patterns:
        return True
    if not paths:
        return True
    for pattern in patterns:
        for path in paths:
            if fnmatch(path, pattern) or fnmatch(path, f"*/{pattern}"):
                return True
            # `**/x` should also match a top-level `x`, which fnmatch does not do.
            if pattern.startswith("**/") and fnmatch(path, pattern[3:]):
                return True
    return False


def convene(
    *,
    run_detectors: bool = True,
    repo_root: Path | None = None,
    seat: str | None = None,
    lane_id: str | None = None,
    all_seats: bool = False,
    paths: list[str] | None = None,
) -> dict:
    """The table's report for a change set, in this tree or another.

    `seat` and `lane_id` convene one reviewer rather than the whole table. An unknown value
    RAISES with the valid set named: silently convening nothing for a typo would report a
    clean review of everything, which is the failure every lane here exists to refuse.

    LANES ARE SELECTED BY RELEVANCE TO THE CHANGE SET, per the standing directive that a
    capability fires when the diff makes it relevant. With 29 seats the unconditional
    listing is a wall nobody reads, and an unread review surface enforces nothing.

    `all_seats=True` convenes every lane regardless -- asking for the whole table directly
    must always be possible, because relevance is an inference about a diff and an operator
    who wants the full bench is not making an inference.
    """
    seats: list[dict] = []
    started = monotonic()
    lanes = _lanes(repo_root)

    selected_by_scope = False
    if not all_seats and seat is None and lane_id is None:
        change_set = changed_paths(repo_root) if paths is None else paths
        relevant = [ln for ln in lanes if lane_is_relevant(ln, change_set)]
        # NEVER NARROW TO NOTHING. An empty table reads as "no questions to ask", which is
        # the one answer a review must never give by accident.
        if relevant:
            selected_by_scope = len(relevant) < len(lanes)
            lanes = relevant

    if seat is not None:
        available = sorted({str(item.get("seat", "?")) for item in lanes})
        matched = [item for item in lanes if str(item.get("seat")) == seat]
        if not matched:
            raise KeyError(f"no seat {seat!r}. Seats at this table: {', '.join(available)}")
        lanes = matched
    if lane_id is not None:
        available = sorted({str(item.get("id", "?")) for item in lanes})
        matched = [item for item in lanes if str(item.get("id")) == lane_id]
        if not matched:
            raise KeyError(f"no lane {lane_id!r}. Lanes here: {', '.join(available)}")
        lanes = matched

    for lane in lanes:
        entry = {
            "seat": lane.get("seat", "?"),
            "lane": lane.get("id", "?"),
            "question": _one_line(lane.get("question")),
            "signature": _one_line(lane.get("signature")),
            # Carried through so the render can name it; absent on the seats that govern
            # review process itself, where inventing a standard would be decoration.
            "standards": list(lane.get("standards") or []),
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
                    clean, detail = _run_detector(lane["detector"], repo_root)
                    entry["clean"] = clean
                    entry["unrunnable"] = detail.startswith(_UNRUNNABLE)
                    entry["detail"] = detail.removeprefix(_UNRUNNABLE)
            # THE SURVEYOR'S REACH, stated rather than assumed. Attribution needs a
            # declared `Module boundary:` clause and most open work orders have none, so a
            # clean Surveyor lane usually means "not judged" rather than "judged and fine".
            # Reported here because a lane whose reach is unknown reads as enforcement and
            # is not -- and because `attribution_reach` with no caller was itself a
            # mechanism that could not do the thing it was built to do (caught by the
            # reachability gate on this change set).
            if lane.get("seat") == "Merge-order steward":
                try:
                    from core.work_orders.admission import attribution_reach

                    entry["attribution_reach"] = attribution_reach()
                except Exception as exc:  # noqa: BLE001 - a report must not fail the table
                    entry["attribution_reach"] = {
                        "status": "unknown",
                        "reason": f"{type(exc).__name__}: {exc}",
                    }
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
        "selected_by_scope": selected_by_scope,
        "detectors_run": len(detectors) if run_detectors else 0,
        "detectors_unclean": [s["lane"] for s in unclean] if run_detectors else [],
        "awaiting_judgment": [s["lane"] for s in seats if s["kind"] != "detector"],
    }


def _render(report: dict) -> str:
    width = _seat_width(report)
    lines: list[str] = ["", "THE ROUND TABLE", ""]

    for seat in report["lanes"]:
        if seat["kind"] != "detector":
            continue
        # THREE MARKS, BECAUSE "NOT RUN" IS NOT "FOUND SOMETHING". Under
        # `--no-detectors` no lane has a `clean` key at all, and a two-way ternary rendered
        # every unrun detector as FOUND -- a reader saw four findings in a listing that
        # checked nothing. That is the Interpreter's own lane on this renderer: a value
        # (absent) displayed as another value's meaning (a finding), the same shape as
        # `not_applicable` drawn as 0% uptime.
        if "clean" not in seat:
            mark = "  -  "
        elif seat["clean"]:
            mark = "clean"
        elif seat.get("unrunnable"):
            # A FOURTH MARK, because "could not be checked" is not "found something". In a
            # skills-only install every detector is absent, and FOUND would report four
            # defects where there are none.
            mark = "UNRUN"
        else:
            mark = "FOUND"
        lines.append(f"  [{mark:>5}] {seat['seat']:<{width}} {seat['lane']}")
        reach = seat.get("attribution_reach") or {}
        if reach.get("status") == "computed":
            lines.append(
                f"          reach: {reach['with_boundary']} of"
                f" {reach['open_work_orders']} open work order(s) declare a boundary"
                f" -- the rest are UNKNOWN, not judged"
            )
        if not seat.get("clean"):
            lines.append(f"          {seat.get('detail', '')}")

    if report.get("selected_by_scope"):
        # A SHORT TABLE MUST NOT READ AS A CLEAN ONE. Naming the omission, and how
        # to undo it, is the difference between a filter and a silent narrowing.
        lines += [
            "",
            "  (lanes irrelevant to this change set were left out -- --all"
            " convenes the whole bench)",
        ]

    awaiting = [s for s in report["lanes"] if s["kind"] != "detector"]
    if awaiting:
        lines += ["", "  ASKED OF YOU — no detector can decide these:", ""]
        for seat in awaiting:
            lines.append(f"  {seat['seat']:<{width}} {seat['question']}")
            lines.append(f"  {'':<{width}} shape: {seat['signature']}")
            # THE STANDARD IS WHAT MAKES A FINDING ARGUABLE ON SOMETHING OTHER THAN
            # SENIORITY. A seat asking a good question against nothing external is one
            # person's taste; naming the published standard gives the author a document
            # to read rather than an opinion to satisfy.
            if seat.get("standards"):
                lines.append(f"  {'':<{width}} standards: {', '.join(seat['standards'])}")
            if seat["kind"] == "graded":
                lines.append(f"  {'':<{width}} fixture: {seat['fixture']}")
            else:
                lines.append(f"  {'':<{width}} unautomatable: {seat['why']}")
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
        unrun = [s["lane"] for s in report["lanes"] if s.get("unrunnable")]
        found = [lane for lane in report["detectors_unclean"] if lane not in unrun]
        parts = []
        if found:
            parts.append(f"{len(found)} detector lane(s) found something — {', '.join(found)}")
        if unrun:
            # Said separately, and still not a pass: a review whose detectors could not run
            # is not a clean review, which is why `status` stays non-pass here.
            parts.append(
                f"{len(unrun)} lane(s) COULD NOT BE CHECKED — {', '.join(unrun)}."
                " Not findings; the detector packages are not installed here"
            )
        lines.append("round-table: " + ". ".join(parts) + ".")
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
    parser.add_argument(
        "--repo-root",
        default=None,
        help=(
            "Convene against THIS project instead of the one the convener lives in. Its"
            " own canonical/review_lanes.yml is read, so a project is asked its own"
            " questions, and each detector is told which tree to scan."
        ),
    )
    parser.add_argument(
        "--all",
        dest="all_seats",
        action="store_true",
        help=(
            "Convene every seat regardless of relevance to the change set."
            " Asking for the whole bench directly must always be possible --"
            " relevance is an inference about a diff, and an operator who wants"
            " all of them is not making one."
        ),
    )
    parser.add_argument(
        "--seat",
        default=None,
        help="Convene one seat alone (exact name). An unknown seat fails, naming the set.",
    )
    parser.add_argument(
        "--lane",
        dest="lane_id",
        default=None,
        help="Convene one lane alone (exact id). An unknown lane fails, naming the set.",
    )
    args = parser.parse_args(argv)

    try:
        report = convene(
            run_detectors=not args.no_detectors,
            repo_root=Path(args.repo_root) if args.repo_root else None,
            seat=args.seat,
            lane_id=args.lane_id,
            all_seats=args.all_seats,
        )
    except (KeyError, FileNotFoundError) as exc:
        # NAMED, NOT SWALLOWED. A typo that convened nothing would print an empty table and
        # exit 0 -- a clean review of everything, which is the substitution every lane here
        # exists to refuse.
        print(f"round-table: {exc}".replace('"', ""), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else _render(report))
    # "unchecked" is a deliberate listing, not a failure -- but it is not a pass
    # either, and the report says so.
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
