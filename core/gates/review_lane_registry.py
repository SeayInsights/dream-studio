"""Gate: a review lane is enforced or declared, never advice.

WHAT THIS IS FOR. Five named reviewers each found a defect nobody else did, and each found
it by asking one repeatable question. Those questions lived in their heads. Writing them
into the review skill's prose would put them exactly where the operator has already said
guidance goes to die: "a lot of prose laid on top of each other as suggestions with no
rules, evals, or really any real test that doing anything they are supposed to."

So `canonical/review_lanes.yml` holds them, and this gate holds the registry to a contract:
every lane carries EXACTLY ONE of

    detector:              a runnable `py -m ...` that decides the lane mechanically
    eval:                  a path under tests/evals/ where a grader decides it
    judgment: true + why:  neither is possible yet, and `why` names WHAT IS MISSING

There is deliberately no fourth option. A lane with no enforcement key is advice; a lane
with two has not decided how it is answered; a `why` that is a shrug is an escape hatch
becoming the norm, which is how a rule turns back into prose.

DELIBERATELY THE SAME SHAPE AS `core/gates/rule_registry.py`, which the operator already
accepted for `canonical/rules.yml` (31 rules, 31 enforced). One enforce-or-declare contract
in this repo, not two that drift.

EVERY LANE ALSO CARRIES ITS PRECEDENT. Each one exists because of a specific finding,
and the finding is the only thing that tells a later reader whether the lane is still worth
asking. A lane with no precedent is someone's hunch with a registry entry.
"""

from __future__ import annotations

import importlib
import json
import shlex
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

REGISTRY = REPO_ROOT / "canonical" / "review_lanes.yml"

#: Exactly one of these answers a lane.
_ENFORCEMENT_KEYS = ("detector", "eval", "judgment")

#: THE ROUND TABLE. Every lane is held by a seat, and a seat says what it watches:
#:
#:   The Warden      is the predicate that admits also the predicate that delivers, or is
#:                   one half enforced by nothing?
#:   The Machinist   which lane actually runs, on which platform, and how long does it take
#:                   when the data is large?
#:   The Archivist   does the decision record name every mechanism the code now depends on?
#:   The Surveyor    how far from base is this, and is it the tree that ships?
#:   The Herald      if a caller sees something different, does the change say so?
#:   The Interpreter does this value reach a reader, and mean there what it meant here?
#:   The Falsifier   this test is green -- show me it going red.
#:   The Custodian   if this record were rebuilt from its events, would it still be here?
#:   The Cartographer what is the full capability surface here, independent of what the
#:                   thing says about itself?
#:
#: THIS LIST WAS THE FIRST FIVE FOR A DAY AFTER IT WAS EIGHT, which is the Archivist's own
#: lane landing on the file that defines the Archivist. Kept in one place with the set
#: below rather than restated anywhere else -- a second copy of a seat roster is a second
#: thing to forget.
#:
#: A CLOSED SET on purpose. These lanes arrived from an external review pass carrying the
#: reviewers' real handles, which is other people's names in a repo with a
#: publication-readiness gate -- and a handle tells a later reader nothing about what the
#: lane watches. Requiring a seat from this set retires the handles for good: a new lane
#: cannot be added under somebody's name, because a name is not a seat.
#:
#: THE INTERPRETER WAS ADDED BY EVIDENCE, and adding a seat is meant to be this hard.
#:
#: A review pass on another project found two defects no seat here would have asked about.
#: A fetch hook returned `{get, isLoading, stateById}` and both views destructured only
#: `get`, so a FAILED FETCH rendered the all-`no_data` placeholder -- a chart asserting
#: "measured, nothing found" when the request had failed. And `not_applicable`, emitted
#: today for agents that do not heartbeat, fell through a renderer's known statuses to a
#: numeric zero and drew as 0% uptime.
#:
#: Every existing seat asks about a mechanism at its own boundary. The Warden compares two
#: predicates, and there was only one site because the consumer did not exist. The Herald
#: asks whether a caller-visible CHANGE was enumerated, and nothing changed -- the value was
#: never consumed at all. The finder's own diagnosis names what was missing: "I verified the
#: hook's state transitions by mutation and stopped at the hook boundary instead of
#: following the values to the pixels", and "I checked that the six axis keys matched the
#: server and never asked what the statuses render as".
#:
#: So the Interpreter asks the terminus question: does this value reach a reader, and does
#: it mean there what it meant here? Widening the Herald was rejected -- its question is
#: about the RECORD of a change, and both defects exist with no change at all, so one lane
#: would answer two questions and stop being falsifiable.
#:
#: THE FALSIFIER AND THE CUSTODIAN, both added on counted evidence rather than for
#: symmetry. The Falsifier owns the family that produced more defects here than any other
#: and had neither gate nor seat: a test whose verdict does not depend on the thing it
#: tests. Every instance -- a byte-hash non-mutation test, a hand-typed control table, two
#: tautologies green under a neutered checker, a `.strip()` whose deletion left 30 tests
#: passing -- was found by an independent auditor and not by the suite. The Custodian asks
#: whether a record survives the machinery that maintains it: 493 of 949 work orders and
#: 1706 of 3286 tasks have no creation event, and `pre_rebuild` truncates before replaying.
#:
#: The Custodian is deliberately NOT the Archivist. That seat asks whether the DECISION
#: record names every mechanism; this asks whether the AUTHORITY record survives a replay.
#: Different records, and merging them would blur both questions into one unanswerable.
#:
#: THE CARTOGRAPHER IS THE NINTH AND THE MOST GENERAL, so it carries the most risk of
#: becoming a shrug -- "did you think of everything?" is unanswerable. It is bounded by the
#: correction its own precedent recorded: derive adversarial inputs from the PARSER's
#: capability surface, not the guard's rule list. For an archive reader that is the format's
#: metadata mechanisms; for a rule it is whether the rule is right; for a producer it is what
#: renders. Not the Falsifier: the ten archive tests COULD have gone red, and passed because
#: the guard really does enforce its caps -- nothing was vacuous. Not the Interpreter: that
#: seat covers only the middle of the three variants.
_SEATS = frozenset(
    {
        "The Warden",
        "The Machinist",
        "The Archivist",
        "The Surveyor",
        "The Herald",
        "The Interpreter",
        "The Falsifier",
        "The Custodian",
        "The Cartographer",
    }
)

#: Prose fields every lane owes a reader, whatever answers it.
#:
#: `measurement` IS IN THIS LIST BECAUSE AN AUDIT FOUND IT MISSING FROM IT. The registry's
#: own header says every lane carries the measurement that decided detector-vs-eval, and
#: `tests/unit/test_review_lane_registry.py` asserts it -- but this tuple did not list it, so
#: the gate passed a registry the test failed, and one lane really was missing it. Three
#: statements of one contract, two of them wrong. The measurement is the load-bearing part:
#: a detector that fires on hundreds of sites is a wall and one that fires on none is
#: decoration, so a lane claiming "not detectable" has to show its work.
_REQUIRED_PROSE = ("question", "signature", "precedent", "measurement")

#: Shorter than this is not a reason, a question, or a precedent. Same bar the
#: `fixture-schema-parity` and `security-scan` exemptions use.
_MIN_PROSE_CHARS = 40


def _load() -> tuple[list[dict], str | None]:
    try:
        data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    except OSError as exc:
        return [], f"{REGISTRY} could not be read ({exc})"
    except yaml.YAMLError as exc:
        return [], f"{REGISTRY} is not parseable YAML ({exc})"
    if not isinstance(data, dict) or not isinstance(data.get("lanes"), list):
        return [], f"{REGISTRY} declares no `lanes:` list"
    return [lane for lane in data["lanes"] if isinstance(lane, dict)], None


def _detector_runnable(command: str) -> str | None:
    """None when the detector can actually be run, else why not.

    IMPORTS THE MODULE AND LOOKS FOR A CALLABLE ``main`` rather than spawning it. A
    subprocess per lane costs 3-12s on Windows, which is what made `rule_registry`'s
    per-check probe take 213s before it was batched -- and a gate nobody can afford to run
    is a gate that gets switched off. Importing proves the same thing the spawn would: the
    module exists, it imports, and there is something to call.
    """
    parts = shlex.split(command)
    if len(parts) < 3 or parts[1] != "-m":
        return f"{command!r} is not of the form `py -m <module>`"
    module_name = parts[2]
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001 - any import failure means not runnable
        return f"{module_name} does not import ({type(exc).__name__}: {exc})"
    entry = getattr(module, "main", None)
    if not callable(entry):
        return f"{module_name} has no callable main(), so `py -m {module_name}` runs nothing"
    return None


def run() -> dict:
    lanes, load_error = _load()
    if load_error:
        return {"status": "fail", "lane_count": 0, "errors": [load_error]}

    errors: list[str] = []
    counts = {"detector": 0, "eval": 0, "judgment": 0}

    if not lanes:
        errors.append(f"{REGISTRY} declares no lanes at all")

    seen: set[str] = set()
    for lane in lanes:
        lane_id = str(lane.get("id") or "").strip()
        if not lane_id:
            errors.append("a lane has no id")
            continue
        if lane_id in seen:
            errors.append(f"{lane_id}: declared twice")
        seen.add(lane_id)

        seat = str(lane.get("seat") or "").strip()
        if seat not in _SEATS:
            errors.append(
                f"{lane_id}: seat {seat!r} is not one of {sorted(_SEATS)}. A lane is held by"
                " a seat that says what it watches, not by whoever happened to find it --"
                " these arrived carrying real reviewer handles and a name describes nothing."
            )

        for field in _REQUIRED_PROSE:
            text = str(lane.get(field) or "").strip()
            if len(text) < _MIN_PROSE_CHARS:
                errors.append(
                    f"{lane_id}: `{field}` is missing or shorter than"
                    f" {_MIN_PROSE_CHARS} characters. A lane without a stated"
                    f" {field} cannot be judged still worth asking."
                )

        present = [key for key in _ENFORCEMENT_KEYS if key in lane]
        if not present:
            errors.append(
                f"{lane_id}: declares no detector, no eval, and no `judgment: true`."
                " That is advice, which is what this registry exists to stop."
            )
            continue
        if len(present) > 1:
            errors.append(
                f"{lane_id}: declares {present} -- exactly one must answer a lane, or"
                " nobody knows which one actually runs."
            )
            continue

        key = present[0]
        counts[key] += 1

        if key == "detector":
            problem = _detector_runnable(str(lane.get("detector") or ""))
            if problem:
                errors.append(f"{lane_id}: detector is not runnable -- {problem}")
        elif key == "eval":
            target = REPO_ROOT / str(lane.get("eval") or "")
            if not target.is_file():
                # "is not a file" rather than "does not exist": a directory-valued `eval:`
                # exists and is still not a grader, and an audit read the old wording as a
                # bug in the check rather than in the registry.
                detail = "is a directory" if target.is_dir() else "does not exist"
                errors.append(
                    f"{lane_id}: eval path {lane.get('eval')!r} {detail}."
                    " A lane pointing at a missing grader is unenforced and says otherwise."
                )
        else:
            if lane.get("judgment") is not True:
                errors.append(
                    f"{lane_id}: `judgment` must be literally true, not {lane['judgment']!r}"
                )
            why = str(lane.get("why") or "").strip()
            if len(why) < _MIN_PROSE_CHARS:
                errors.append(
                    f"{lane_id}: declared judgment with no usable `why` ({why!r})."
                    " Name what is missing that stops this being a detector or an eval,"
                    f" in at least {_MIN_PROSE_CHARS} characters, so someone can later"
                    " close it."
                )

    return {
        "status": "fail" if errors else "pass",
        "lane_count": len(lanes),
        "detector": counts["detector"],
        "eval": counts["eval"],
        "judgment": counts["judgment"],
        "errors": errors,
    }


def main() -> int:
    result = run()
    if result["status"] != "pass":
        print(json.dumps(result, indent=2, sort_keys=True))
        print(
            "\nreview-lane-registry: FAILED. Every lane in canonical/review_lanes.yml must"
            " be answered by a runnable detector, a graded eval, or a declared judgment"
            " with a reason.",
            file=sys.stderr,
        )
        return 1
    print(
        f"review-lane-registry: OK - {result['lane_count']} lane(s):"
        f" {result['detector']} detector, {result['eval']} eval,"
        f" {result['judgment']} declared judgment."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
