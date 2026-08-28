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

from core.gates.evidence_backed_output import _CITATION

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
                f"unverified-claims: OK - every asserted absence cites a look "
                f"({self.citations} citation(s) present)"
            )
        lines = [
            f"unverified-claims: {len(self.unverified)} asserted absence(s) with nothing "
            "cited. Each of these is a claim about the existing system that a single "
            "command would settle:"
        ]
        for claim in self.unverified:
            lines.append(f"  line {claim.line} ({claim.trigger!r})")
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
            )
        )
    return report
