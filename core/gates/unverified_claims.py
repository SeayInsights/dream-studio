"""An asserted absence must cite the look that established it.

Operator ruling 2026-08-28: "those gates need to be adjusted so that you have to look
without assuming."

WHAT THIS CATCHES, and why it is a distinct failure from a hedge. The
``evidence-backed-output`` gate catches an author who is UNSURE and says so without
citation ("should pass", "expected to"). This catches the opposite and more dangerous
posture: an author who is CONFIDENT about a property of the existing system and never
checked it. Confident and wrong reads as fact, so nothing downstream questions it.

MEASURED ACROSS ONE SESSION, all mine, all avoidable by looking first:

* A work order registered claiming an unprojectable event "retries forever and blocks the
  queue". The projection framework already dead-letters after max retries and explicitly
  continues -- and the live engine demonstrated it while the registration was still being
  written. The task had to be retitled "NO WORK NEEDED".
* A gap-attribution mechanism built on declared module boundaries before measuring that
  only 3 of 122 open work orders declare one. Correct, and inert.
* "No gate covers this" -- said about a class two existing gates partly covered.
* "The push landed clean" -- reported without reading the result; it had been refused.
* "Zero failures so far" -- from a grep that could only ever match pytest's end-of-run
  summary, so it could not have seen a failure.

THE SIGNATURE IS ASSERTED ABSENCE. "Nothing does X." "No gate covers this." "It has no
caller." "X does not exist." Those are claims about the state of a system, they are cheap
to check, and each one above would have been caught by a single command.

SO: a description that asserts an absence must carry a citation -- a command and its
output, a count, a file:line, a grep, a measured number. This does NOT block registering a
defect; a defect must always be registerable, and blocking that would trade a small error
for a large one. It records which claims went unchecked, on the record, where a close gate
and a human reviewer can both see them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# What counts as having actually LOOKED. Moved here from the deleted
# evidence_backed_output gate, which was its only other home: that gate audited
# whether the platform's own PR text cited evidence, which is a writing-style
# check on the bureaucracy, not a check on whether Dream Studio works. This regex
# was the one piece of it doing real work, so it moved rather than died.
_CITATION = re.compile(
    r"("
    r"\d+\s+(passed|failed|skipped|xfailed|errored)"  # a count with its unit
    r"|::[A-Za-z_][A-Za-z0-9_]*"  # a test node id
    r"|[\w./\\-]+\.(py|md|yaml|json|txt):\d+"  # file:line
    r"|\b[0-9a-f]{7,40}\b"  # commit sha
    r"|Overall:\s*(PASS|FAIL)"  # gate verdict
    r"|\bid=\d+|\brun[s]?/\d+"  # run id
    r"|`[^`]+`"  # a named artifact or command
    r"|\bmeasured\b|\bverified by\b|\breproduced\b"  # an explicit provenance claim
    # The commands people actually establish an ABSENCE with. Omitting these left the
    # unverified-claims gate unable to recognise the most common form of looking:
    # "grep -rn X core/ -> 0 hits" is precisely the evidence it exists to ask for, and it
    # was being reported as an unchecked claim.
    r"|\bgrep\b|\brg\b|\bls-files\b|\bcheck-ignore\b|\bfind \.|\bwc -l\b"
    r"|->\s*\d+\s*(hits?|rows?|matches|files?)"
    r")",
    re.IGNORECASE,
)

# Asserted absence or asserted totality about the existing system. Deliberately narrow:
# these are claims of fact, not expressions of intent. "X must not happen" is a rule;
# "X does not happen" is a claim.
_ABSENCE = re.compile(
    r"("
    r"nothing (?:does|checks|reads|surfaces|catches|enforces|prevents|stops|calls|uses)"
    r"|no (?:gate|test|caller|call site|check|reader|consumer|hook|mechanism|coverage)\b"
    r"|(?:does|do|did) not exist|doesn't exist|never exist"
    r"|has no (?:caller|call site|test|reader|consumer|owner)"
    r"|is not (?:wired|reachable|called|tested|covered|surfaced)"
    r"|(?:are|is) never (?:surfaced|called|read|checked|reached)"
    r"|there (?:is|are) no\b"
    r"|retries forever|loops forever|blocks the queue"
    r"|only (?:place|site|caller|consumer)\b"
    r"|nowhere\b|unreachable\b"
    r")",
    re.IGNORECASE,
)


# A STATED MEASUREMENT IS A CLAIM OF FACT. `_ABSENCE` catches "nothing does X"; this
# catches "457 of 1,387 do X", which is the same posture -- confident about a property of
# the existing system -- and just as cheap to settle. It is not a hypothetical class:
# every one of these was stated with confidence in this repository and shaped later work
# before anyone re-derived it.
#
#   "457 of 1,387 TEST-CHECKs name something unrunnable"  counted a SUPPORTED form
#                                                         (`cmd:`) as junk
#   "96 files claim generation with no runnable generator" 85% of them were either
#                                                         already checked or prose
#   "1 skills registered"                                 the number was right and the
#                                                         meaning was not
#   "every agent sees ~60 modes per turn"                 wrong in the opposite direction
#   "70% compatibility bug reduction"                     no source, ever
#
# Deliberately narrow, and measured before it shipped: across the 830-line CHANGELOG it
# matches 62 lines, of which 45 already carry a citation and 6 are attributed. A pattern
# that flags almost nothing is noise-free and useless; one that flags almost everything
# is a wall. Eleven is a worklist.
#
# A bare count of what a change DID ("adds 3 tests") is not matched: the shapes here are
# proportions and totalities -- N of M, a percentage, "all N", "every N" -- which are
# assertions about a population somebody had to go and count.
_QUANTITY = re.compile(
    r"("
    r"\b\d[\d,]*\s+of\s+\d[\d,]*\b"
    r"|\b\d[\d,]*\s*%"
    r"|\ball (?:of )?(?:the )?\d[\d,]*\b"
    r"|\bevery (?:one of )?(?:the )?\d[\d,]*\b"
    r"|\b(?:zero|none) of\b"
    r")",
    re.IGNORECASE,
)

# A claim that quotes or attributes is reporting, not asserting -- the same distinction
# the evidence gate had to draw for hedges inside quotations.
_ATTRIBUTED = re.compile(
    r"(previously said|used to|before this|was false|the grader (?:said|reported|named)"
    r"|CORRECTED|it turned out|I claimed|I said|registered on a false premise)",
    re.IGNORECASE,
)


@dataclass
class Claim:
    line: int
    trigger: str
    text: str
    #: "absence" or "quantity" -- a reader fixes them differently. An absence needs the
    #: command that established it; a measurement needs how it was counted.
    kind: str = "absence"


@dataclass
class Report:
    unverified: list[Claim] = field(default_factory=list)
    citations: int = 0

    @property
    def passed(self) -> bool:
        return not self.unverified

    def render(self) -> str:
        if self.passed:
            return (
                f"unverified-claims: OK - every asserted absence and measurement cites "
                f"a look ({self.citations} citation(s) present)"
            )
        lines = [
            f"unverified-claims: {len(self.unverified)} claim(s) with nothing cited. "
            "Each is a statement about the existing system that a single command would "
            "settle:"
        ]
        for claim in self.unverified:
            lines.append(f"  line {claim.line} [{claim.kind}] ({claim.trigger!r})")
            lines.append(f"    {claim.text}")
        lines.append(
            "\n  Run the check and paste what it said. A confident claim that was never "
            "looked up reads as fact, so nothing downstream questions it -- which is worse "
            "than an admitted guess."
        )
        return "\n".join(lines)


def audit_claims(text: str) -> Report:
    """Find asserted absences in a description that cite nothing.

    Citation is looked for on the claim's own line or the two lines beneath it, matching
    the evidence gate's window: evidence is normally pasted under the sentence it
    supports.
    """
    lines = text.splitlines()
    report = Report()

    for index, line in enumerate(lines):
        report.citations += len(_CITATION.findall(line))

        match = _ABSENCE.search(line)
        kind = "absence"
        if not match:
            match = _QUANTITY.search(line)
            kind = "quantity"
        if not match:
            continue
        if _ATTRIBUTED.search(line):
            continue  # reporting someone else's claim, or correcting one's own

        # A QUOTED claim is being reported, not made. Found by running this gate on the
        # pull-request body that introduces it: a "Claim | Reality" table quoting my own
        # false statements was flagged as making them. The evidence-backed-output gate had
        # to draw the same distinction for hedges inside quotations.
        #
        # It is the same accepted hole: an author can wrap an assertion in quotes to slip
        # it past. A quoted claim reads as attribution, and flagging every correction table
        # would penalise exactly the behaviour this gate exists to encourage.
        span = match.span()
        start, end = span
        before, after = line[:start], line[end:]
        quote_marks = ('"', "'", "`", "\u201c", "\u201d")
        if any(q in before and q in after for q in quote_marks):
            continue

        window_end = min(len(lines), index + 3)
        window = lines[index:window_end]
        if any(_CITATION.search(candidate) for candidate in window):
            continue

        report.unverified.append(
            Claim(
                line=index + 1,
                trigger=match.group(0),
                text=" ".join(line.split())[:150],
                kind=kind,
            )
        )
    return report


# ---------------------------------------------------------------------------
# CLI door
#
# `audit_claims` had two callers and no command. `core/skills/git.md` told an
# author to run `py -m core.gates.evidence_backed_output <pr-body.md>` before
# publishing an outbound document -- and that sibling gate was culled in 67ba10e,
# so the instruction named a module that no longer exists. The check it was
# reaching for survives here; only its door went with the sibling.
#
# A check with no command is a check an author cannot run, which is the same
# defect as a command that names nothing.
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Audit a document, or this push's own outbound text, for uncited claims.

    Exit 0 when every asserted absence cites a look, 1 otherwise.
    """
    import argparse
    import subprocess
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(
        prog="py -m core.gates.unverified_claims",
        description="An asserted absence must cite the look that established it.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("path", nargs="?", help="A document to audit (a PR body, a report)")
    source.add_argument(
        "--staged",
        action="store_true",
        help="Audit what this push publishes: staged commit messages plus added CHANGELOG lines",
    )
    args = parser.parse_args(argv)

    if args.staged:
        # The two things a push actually publishes to somebody else.
        # encoding= IS LOAD-BEARING HERE, and the locale-decode gate caught its absence
        # on the first run. Without it Windows decodes child output with cp1252, and one
        # unmapped byte raises inside subprocess's reader thread: run() then returns
        # returncode=0 with stdout=None, so the caller is handed success and no text.
        # This reads commit messages, which in this repository are full of em-dashes.
        messages = subprocess.run(
            ["git", "log", "--format=%B", "origin/main..HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        ).stdout
        diff = subprocess.run(
            ["git", "diff", "origin/main...HEAD", "--", "CHANGELOG.md"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        ).stdout
        added = "\n".join(
            line[1:] for line in diff.splitlines() if line.startswith("+") and line[1:2] != "+"
        )
        text = messages + "\n" + added
    else:
        candidate = Path(args.path)
        if not candidate.is_file():
            print(f"error: no such file: {candidate}", file=sys.stderr)
            return 1
        text = candidate.read_text(encoding="utf-8", errors="replace")

    report = audit_claims(text)
    print(report.render())
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
