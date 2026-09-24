"""Render the review skill's bench listing from the registry that defines it.

THE SECTION SAID IT WAS GENERATED AND WAS NOT. `canonical/skills/core/modes/review/
SKILL.md` heads its lane listing with "this section is GENERATED from it", warns in its own
next line that "a hand-maintained copy of a registry is a second vocabulary that silently
disagrees with the first", and was then hand-maintained. Nothing rendered it: the
generated-artifacts gate registered `canonical/review_lanes.yml` and the reviewer agents,
and no third entry.

So it drifted, and it drifted in the direction that matters. It announced a bench of **29
seats** and enumerated seats the registry no longer has -- Merge-order steward,
Test-integrity inquisitor, Distributed state and concurrency, Event-substrate custodian --
while the live registry is 10 seats and 26 lanes. That is the document the dispatch rule
points a subagent at, so the wrong bench is what a reviewer was told to convene.

This renders it, and the gate checks it. The counts are computed, so no one can write a
number here again.

WHAT IT DOES NOT GENERATE. Only the bench listing, between the markers. Everything else in
that skill -- the two-stage order, the dispatch loop, the operator rules -- is authored
prose about a process, and a generator that owned it would be inventing the process from a
data file that does not describe one.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / "canonical" / "skills" / "core" / "modes" / "review" / "SKILL.md"

BEGIN = "<!-- GENERATED:bench begin -- py -m integrations.compiler.review_skill --write -->"
END = "<!-- GENERATED:bench end -->"


def _lanes() -> list[dict[str, Any]]:
    """The registry, through the round table's own loader.

    Not a third parse of the file: the round table's loader already refuses a missing or
    empty registry -- "a convening with no lanes is not a clean review" -- and a listing
    rendered from a second loader without that guard would render an empty bench as
    current.
    """
    from core.gates.round_table import _lanes as registry_lanes

    return registry_lanes()


def _kind(lane: dict[str, Any]) -> str:
    """The round table's vocabulary for how a lane is answered: detector, graded, judgment."""
    if "detector" in lane:
        return "detector"
    if "eval" in lane:
        return "graded"
    return "judgment"


def render() -> str:
    """The bench, as the registry currently defines it."""
    lanes = _lanes()
    seats: dict[str, list[dict[str, Any]]] = {}
    for lane in lanes:
        seats.setdefault(str(lane.get("seat", "")).strip() or "(unseated)", []).append(lane)

    counts = {
        k: sum(1 for ln in lanes if _kind(ln) == k) for k in ("detector", "graded", "judgment")
    }

    out: list[str] = [BEGIN, ""]
    out.append(
        f"The bench is **{len(seats)} seats** and **{len(lanes)} lanes**: "
        f"{counts['detector']} answered by a detector, {counts['graded']} graded by an eval, and "
        f"{counts['judgment']} by judgment — which is what the reviewer agents are for."
    )
    out.append("")
    out.append("| Seat | Lanes | Answered by |")
    out.append("| --- | --- | --- |")
    for seat in sorted(seats):
        owned = seats[seat]
        kinds = sorted({_kind(ln) for ln in owned})
        ids = ", ".join(
            f"`{ln.get('id')}`" for ln in sorted(owned, key=lambda ln: str(ln.get("id")))
        )
        out.append(f"| {seat} | {ids} | {', '.join(kinds)} |")
    out.append("")
    out.append(
        "Each seat but the chair compiles to an agent under `canonical/agents/review-*.md`"
        " carrying its own lanes — the question, the defect signature, the precedent it came"
        " from and the governing standard. The chair has no agent: a subagent sees only its"
        " own lanes, and reconciling findings it was never given is not a question it can"
        " answer. **The caller is the chair.**"
    )
    out.append("")
    out.append(END)
    return "\n".join(out)


def _splice(text: str, block: str) -> str:
    start = text.find(BEGIN)
    end = text.find(END)
    if start == -1 or end == -1:
        raise SystemExit(
            f"{SKILL} has no generated-bench markers. Add {BEGIN!r} and {END!r} around the"
            " bench listing, or this generator has nothing to own."
        )
    after = end + len(END)
    return text[:start] + block + text[after:]


def check() -> tuple[bool, str]:
    """Is the skill's bench listing what the registry says today?"""
    if not SKILL.is_file():
        return False, f"{SKILL.relative_to(REPO_ROOT)} is missing"
    text = SKILL.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        return False, "the review skill has no generated-bench markers"
    head, tail = text.find(BEGIN), text.find(END) + len(END)
    current = text[head:tail]
    if current.strip() != render().strip():
        return False, "the review skill's bench listing has drifted from canonical/review_lanes.yml"
    lanes = _lanes()
    return True, f"the review skill names the registry's {len(lanes)} lanes"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if "--write" in args:
        text = SKILL.read_text(encoding="utf-8")
        SKILL.write_text(_splice(text, render()), encoding="utf-8")
        ok, detail = check()
        print(f"review skill bench: {detail}")
        return 0 if ok else 1
    ok, detail = check()
    print(f"review skill bench: {'OK' if ok else 'STALE'} - {detail}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
