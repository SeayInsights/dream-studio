"""Everything Dream Studio pushes outward must show its evidence.

Operator ruling 2026-08-27: "any comment or review being pushed to github has to be backed
by evidence and show all evidence and everything has to be verified. it should be detailed
and based on facts and show all facts so no one is ever guessing."

SCOPE: what Dream Studio EMITS -- pull-request bodies, PR review comments, issue comments,
release notes. The code under review is the SDLC baseline's job; this is about DS's own
outbound claims.

THE RULE WAS ALREADY BEING BROKEN WHEN IT WAS WRITTEN. Measured across the four PR bodies
authored in the session that produced this module, all four carried the checklist line:

    - [x] PR smoke is expected to pass

A prediction, inside a CHECKED box. Three of those pull requests were already merged. Two
more from the same session: a maintenance action described as "now-repeatable" while it had
no call site at all, and "zero failures so far" reported from a grep that could only ever
match pytest's end-of-run summary. Each read as fact. None was one.

WHY THIS IS ENFORCEABLE AND NOT A STYLE PREFERENCE. The distinguishing feature of a guess
is that it cites nothing a reader can go and check. A claim is evidence-backed when it
carries at least one of:

  * a command and its output
  * a test node id, or a count with its unit ("306 passed")
  * a file:line reference
  * a measured number together with its source
  * a named artifact -- commit sha, run id, verdict path

A claim carrying none of those, and especially a HEDGED one, is a guess. That is a
computable property, which is what makes it a gate rather than an aspiration.

WHAT THIS DELIBERATELY DOES NOT CATCH:

  * A confident sentence that is simply wrong. Nothing textual can catch that; the fix is
    running the check, not scanning the prose.
  * A claim whose evidence sits elsewhere in the document. Citation is looked for on the
    claim's own line, or in an output block directly beneath it -- NOT on the preceding
    line, and not anywhere nearby. The first version accepted any adjacent line and was
    nearly useless because of it: in a document that cites heavily (the PR body that
    motivated this module carries 46 citations) almost every line has a cited neighbour,
    so an unrelated citation laundered the hedge beside it. So a well-evidenced claim
    written far from its evidence IS reported. Reported findings are cheap to dismiss;
    missed guesses are not.
  * A hedge inside a QUOTATION. Quoting the offending line is how a document explains
    the rule -- this module's docstring, the pre-push gate entry, and the commit that
    introduced the rule all quote "- [x] PR smoke is expected to pass" verbatim. Flagging
    those made the gate refuse the documents explaining it. An author can therefore evade
    it by wrapping a claim in quotes, which is a real hole and the accepted cost: a quoted
    claim reads as attribution, and blocking every document that documents the rule is the
    worse trade.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Words that assert something the author has not established. Deliberately narrow: these
# are claims about state, not ordinary uncertainty about opinion.
_HEDGE = re.compile(
    r"\b("
    r"expected to (pass|work|succeed|be)"
    r"|should (pass|work|succeed|be fine|hold)"
    r"|probably|presumably|likely to|ought to (pass|work)"
    r"|seems to (pass|work|be)|appears to (pass|work|be)"
    r"|I (believe|think|assume)|no reason to think"
    r"|as far as I can tell|in theory"
    r")\b",
    re.IGNORECASE,
)

# Things a reader can independently check.
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

# A checked box asserts the item is done. An unchecked one asserts nothing.
_CHECKED_BOX = re.compile(r"^\s*[-*]\s*\[[xX]\]\s*(?P<text>.+)$")


@dataclass
class Claim:
    """One outbound sentence that asserts something it does not substantiate."""

    line: int
    trigger: str
    text: str
    kind: str  # "hedged" | "checked-box"

    def render(self) -> str:
        return f"  line {self.line} ({self.kind}, {self.trigger!r})\n    {self.text}"


@dataclass
class Report:
    """What the text claims, and what it can prove."""

    unbacked: list[Claim] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.unbacked

    def render(self) -> str:
        lines: list[str] = []
        if self.unbacked:
            lines.append(
                f"evidence-backed-output: FAIL - {len(self.unbacked)} claim(s) cite "
                "nothing a reader can check:"
            )
            lines.extend(claim.render() for claim in self.unbacked)
        else:
            lines.append("evidence-backed-output: OK - every claim cites something checkable")

        # SHOW WHAT WAS FOUND, not only what is missing. "Unbacked claim at line 12" is
        # half an answer: an author needs to see the evidence the document DOES carry to
        # know what the gap is. Holding the report to the same standard it imposes.
        if self.evidence:
            lines.append(f"\n  evidence present ({len(self.evidence)} citation(s)):")
            lines.extend(f"    {item}" for item in self.evidence[:12])
            if len(self.evidence) > 12:
                lines.append(f"    ... and {len(self.evidence) - 12} more")
        else:
            lines.append(
                "\n  evidence present: NONE. A document making claims about verified work "
                "with no citation at all is the case this gate exists for."
            )
        return "\n".join(lines)


def _is_quoted(line: str, start: int, end: int) -> bool:
    """Does the span ``[start:end)`` sit inside a quotation on this line?

    A HEDGE INSIDE A QUOTATION IS EVIDENCE OF A DEFECT, NOT AN INSTANCE OF ONE. This
    module's own docstring, the pre-push gate's description, and the commit that added the
    rule all quote the real offending line -- "- [x] PR smoke is expected to pass" -- in
    order to say what must not be written. Flagging those made the gate refuse the very
    documents explaining it, which is unusable rather than strict.

    The first version accepted that as a documented false positive on the grounds that the
    alternative "can be evaded by quoting". That reasoning was wrong in one direction and
    right in another: an author CAN wrap a claim in quotes to slip it past. But a quoted
    claim reads as attribution -- "X reported Y" -- and an unattributed quotation of one's
    own forecast is a different and rarer failure than the one this gate exists to stop.
    Blocking every document that documents the rule is the worse trade.
    """
    before = line[:start]
    after = line[end:]
    for mark in ('"', "'", "`"):
        if mark in before and mark in after:
            return True
    return False


def _quote_open_at_line_start(lines: list[str], index: int) -> bool:
    """Is a double quote still open when this line begins?

    A MULTI-LINE QUOTATION IS THE NORMAL CASE, NOT AN EDGE CASE. Commit messages wrap at
    72 characters, so quoting the offending line almost always splits it:

        four PR bodies written the day this was built carried "- [x] PR smoke is
        expected to pass", a forecast inside a checked box

    The single-line check sees a closing quote after the hedge on the second line and no
    opening one before it, so it reported the quotation as a claim -- and the gate refused
    two of the commits that introduced it. Parity of double quotes over the preceding
    lines answers this exactly for well-formed text.

    Only double quotes are tracked. Apostrophes appear in ordinary prose ("doesn't"), so
    parity on `'` would drift immediately, and backticks are handled per line because
    inline code spans do not wrap.
    """
    return sum(line.count('"') for line in lines[:index]) % 2 == 1


def _looks_like_output(line: str) -> bool:
    """Is this line the OUTPUT of the claim above it, rather than another claim?

    Output is indented, fenced, or quoted -- the conventions people already use when
    pasting a command result under the sentence it supports.
    """
    if not line.strip():
        return False
    return line.startswith((" ", "	", "```", ">", "|")) or line.lstrip().startswith("$")


def _has_citation(lines: list[str], index: int) -> bool:
    """Is THIS claim cited -- on its own line, or in the output block directly beneath it?

    THE WINDOW WAS TOO WIDE AND THE GATE WAS NEARLY USELESS BECAUSE OF IT. The first
    version accepted a citation on any adjacent line, including the PRECEDING one. In a
    document that cites heavily -- the PR body that motivated this gate carries 46
    citations -- almost every line has a cited neighbour, so an unrelated citation
    laundered the hedge next to it and the gate passed nearly everything. It was weakest
    on exactly the documents it exists to check.

    Caught by test_the_report_shows_the_evidence_found: "The rest should work." went
    unflagged because the line ABOVE it happened to mention a commit sha.

    Now: the claim's own line, or a following line that looks like output. A preceding
    line is never evidence for a later claim -- it is evidence for itself.
    """
    if _CITATION.search(lines[index]):
        return True
    for offset in (1, 2):
        nxt = index + offset
        if nxt >= len(lines):
            break
        if not _looks_like_output(lines[nxt]):
            break
        if _CITATION.search(lines[nxt]):
            return True
    return False


def audit_text(text: str) -> Report:
    """Report the unbacked claims in one outbound document, and the evidence it carries."""
    lines = text.splitlines()
    report = Report()

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        for match in _CITATION.finditer(line):
            token = match.group(0).strip()
            if token and token not in report.evidence:
                report.evidence.append(token)

        # An UNCHECKED box is an admission, not a claim. Judging its wording would push
        # an author toward ticking it rather than leaving it honest -- the opposite of the
        # rule. Checked earlier than the hedge test, because the hedge test cannot tell.
        if re.match(r"^\s*[-*]\s*\[[ ]\]", line):
            continue

        hedge = _HEDGE.search(line)

        # SPECIFIC BEFORE GENERAL. A checked box says "this is done" while its words admit
        # it is not -- a self-contradiction worth naming as such. The generic hedge branch
        # used to fire first and `continue`, so these were reported as ordinary prose and
        # the most actionable finding lost its label.
        box = _CHECKED_BOX.match(line)
        if box:
            box_hedge = _HEDGE.search(box.group("text"))
            box_quoted = box_hedge and (
                _is_quoted(line, *box_hedge.span()) or _quote_open_at_line_start(lines, index)
            )
            if box_hedge and not box_quoted and not _has_citation(lines, index):
                report.unbacked.append(
                    Claim(
                        line=index + 1,
                        trigger=box_hedge.group(0),
                        text=stripped[:120],
                        kind="checked-box",
                    )
                )
            continue

        quoted = _is_quoted(line, *hedge.span()) if hedge else False
        if hedge and not quoted and _quote_open_at_line_start(lines, index):
            quoted = True  # the quotation opened on an earlier line and has not closed
        if hedge and not quoted and not _has_citation(lines, index):
            report.unbacked.append(
                Claim(
                    line=index + 1,
                    trigger=hedge.group(0),
                    text=stripped[:120],
                    kind="hedged",
                )
            )

    return report


def audit_file(path: Path) -> Report:
    """Audit one outbound document on disk."""
    return audit_text(Path(path).read_text(encoding="utf-8"))


def staged_outbound_documents(
    base_ref: str = "main", *, repo_root: Path | None = None
) -> list[tuple[str, str]]:
    """The outbound text this push will publish, as ``(label, content)`` pairs.

    WHAT IS ACTUALLY OUTBOUND. A pull-request body does not live in the repository, so a
    gate running from a git hook cannot find one -- and claiming to audit PR bodies here
    would be exactly the unbacked assertion this module exists to stop. What a push really
    publishes:

      * the COMMIT MESSAGES of the commits being pushed, which appear on GitHub verbatim
      * lines ADDED to CHANGELOG.md, which are published release notes

    Only ADDED changelog lines: existing entries are already published and are not this
    push's claims to answer for.

    A PR body is still auditable by path through the CLI. It simply is not discoverable
    from inside the repo, and this says so instead of pretending otherwise.
    """
    import subprocess

    root = (repo_root or Path.cwd()).resolve()

    def _git(*args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout if result.returncode == 0 else ""

    documents: list[tuple[str, str]] = []

    shas = [s.strip() for s in _git("rev-list", f"{base_ref}..HEAD").splitlines() if s.strip()]
    for sha in shas:
        body = _git("log", "-1", "--format=%B", sha)
        if body.strip():
            documents.append((f"commit {sha[:8]}", body))

    diff = _git("diff", f"{base_ref}...HEAD", "--", "CHANGELOG.md")
    added = [
        line[1:]
        for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    if added:
        documents.append(("CHANGELOG.md (added lines)", "\n".join(added)))

    return documents


def _audit_staged() -> int:
    """Audit everything this push publishes. Returns a process exit code."""
    documents = staged_outbound_documents()
    if not documents:
        print(
            "evidence-backed-output: OK - this push publishes no commit messages or "
            "changelog lines to audit"
        )
        return 0

    failed = False
    for label, content in documents:
        report = audit_text(content)
        if not report.passed:
            print(f"== {label} ==")
            print(report.render())
            print()
            failed = True

    if not failed:
        print(
            f"evidence-backed-output: OK - {len(documents)} outbound document(s) checked, "
            "every claim cites something checkable"
        )
        return 0

    print(
        "  Every claim pushed to GitHub must show its evidence. Replace each claim above\n"
        "  with the fact it rests on -- a command and its output, a test count, a\n"
        "  file:line, a commit sha, a run id -- or delete the claim. A checked box that\n"
        "  says 'expected to' is a forecast, not a check."
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if "--staged" in args:
        return _audit_staged()
    if not args:
        print(
            "evidence-backed-output: no document supplied.\n"
            "  usage: py -m core.gates.evidence_backed_output <pr-body.md> [...]\n"
            "     or: py -m core.gates.evidence_backed_output --staged"
        )
        return 0

    failed = False
    for name in args:
        path = Path(name)
        if not path.is_file():
            print(f"evidence-backed-output: {name} is not a readable file")
            failed = True
            continue
        report = audit_file(path)
        print(f"== {name} ==")
        print(report.render())
        print()
        if not report.passed:
            failed = True

    if failed:
        print(
            "  Every claim pushed to GitHub must show its evidence. Replace each claim\n"
            "  above with the fact it rests on -- a command and its output, a test count,\n"
            "  a file:line, a commit sha, a run id -- or delete the claim. A checked box\n"
            "  that says 'expected to' is a prediction, not a check."
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
