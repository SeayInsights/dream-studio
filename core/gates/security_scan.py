"""Gate: a changed file may not introduce a security anti-pattern.

THE DEFECT THIS EXISTS FOR, measured 2026-09-08. A live shell injection sat in
``control/execution/workflow/runner.py`` -- a node's own output reached
``subprocess.run(check, shell=True)`` as code, and the injected command's exit status
became the node's verification evidence (WO 26675b56). DS has carried a ``shell=True``
detector the whole time. Called against that file's content, ``scan_for_patterns`` returned
``[]``.

FOUR REASONS, each measured, and only one of them was the regex:

1. THE PATTERN COULD NOT CROSS A NEWLINE. ``subprocess[^\\n]+shell\\s*=\\s*True`` requires
   the token and the keyword on one line, and black formats any multi-argument call across
   lines. Counted over ``git ls-files *.py`` by walking each call's parenthesis depth: 56
   subprocess call sites are single-line, 189 span lines -- blind to 77% of them. Fixed by
   PARSING (``security_patterns.parsed_findings``), which has no window to get wrong.

2. IT COULD NOT BLOCK. The hook prints a warning and returns; there is no deny path in it.
   It is also PostToolUse, so the edit has already been applied by the time it runs --
   blocking is not available there at all. THIS GATE IS THE BLOCKING TIER.

3. IT SCANNED A FRAGMENT. ``extract_content`` returns an ``Edit``'s ``new_string``. For a
   realistic payload that is ``'    shell=True,'``: unparseable, and missing the
   ``subprocess`` token the old pattern also required.

4. THE DOMINANT ONE, AND WHY A HOOK CANNOT BE THE ANSWER: a file written WITHOUT the
   Edit/Write tools fires no hook at all. A patch script calling ``write_text``, a merge, a
   rebase, a generated projection -- none of them. Every change in the session that found
   this defect landed that way. So the check has to run over changed FILES, which is what
   this does.

A FIFTH claim I made and had to withdraw: I reported that the hook was unwired because
``on-security-scan`` appears nowhere in ``hooks/hooks.json``. The grep was right and the
conclusion was wrong -- ``runtime/hooks/meta/on-edit-dispatch.py`` invokes it and hooks.json
wires that dispatcher to PostToolUse. Recorded here because the correction is the useful
part: searching a manifest for a literal name misses a layer of indirection, which is the
same mistake as measuring whether a key is present instead of what its value is.

DIFF-SCOPED, like ``workflow-node-verification`` and ``normative-baseline``. The tracked
tree currently has ZERO findings, so a whole-tree scan would pass today -- but scoping to
the diff keeps it that way as the tree grows without ever becoming a wall someone switches
off.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from control.analysis.security_patterns import findings_with_lines, should_scan

REPO_ROOT = Path(__file__).resolve().parents[2]

#: An author who genuinely needs one of these declares it on the finding's own line, with a
#: reason. The mandatory reason follows `fixture-schema-parity`'s precedent: an escape hatch
#: without one becomes the norm, which is how a rule turns back into prose.
_EXEMPTION = re.compile(r"#\s*security-scan:\s*(?P<reason>\S.*)")

#: Shorter than this is not a reason.
_MIN_REASON_CHARS = 20


def changed_scannable_files(base_ref: str | None = None) -> list[str]:
    """Files this change set touches that the scanner accepts.

    Untracked files are included: ``git diff`` never reports one, and a brand-new file is
    exactly the case a security gate most needs to see. The ``gitignore-phantom`` gate was
    written after that same blind spot.
    """
    base = base_ref or os.environ.get("DREAM_STUDIO_BASE_REF") or "origin/main"
    paths: set[str] = set()
    for argv in (
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        ["git", "diff", "--name-only", "--cached"],
        ["git", "diff", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        try:
            proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
                argv,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode != 0:
            continue
        for line in (proc.stdout or "").splitlines():
            name = line.strip().replace("\\", "/")
            if name and should_scan(name, include_tests=True) and (REPO_ROOT / name).is_file():
                paths.add(name)
    return sorted(paths)


def _statement_start(content: str, number: int) -> int | None:
    """The first line of the smallest statement containing line ``number``.

    Needed because a finding can sit inside a MULTI-LINE LITERAL, where no comment can be
    adjacent to it: a credential-shaped line inside a triple-quoted test fixture cannot
    carry a `#` without changing the fixture. The declaration then belongs above the
    statement, which is where a reader would look anyway.

    Uses the same parser as the code-shape pass, so this costs nothing extra. Returns None
    for content that will not parse, and the caller simply falls back to the line walk.
    """
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError):
        return None
    best: int | None = None
    for node in ast.walk(tree):
        start = getattr(node, "lineno", None)
        end = getattr(node, "end_lineno", None)
        if not isinstance(node, ast.stmt) or start is None or end is None:
            continue
        if start <= number <= end and (best is None or start > best):
            best = start
    return best


def _contiguous_comment_reason(lines: list[str], index: int) -> str | None:
    """A declaration on line ``index`` (0-based) or in the comment block directly above it.

    CONTIGUOUS on purpose, at every anchor point: an unrelated comment further up the file
    must not reach down and silence something.
    """
    if 0 <= index < len(lines):
        match = _EXEMPTION.search(lines[index])
        if match:
            return match.group("reason").strip()
    cursor = index - 1
    while 0 <= cursor < len(lines) and lines[cursor].lstrip().startswith("#"):
        match = _EXEMPTION.search(lines[cursor])
        if match:
            return match.group("reason").strip()
        cursor -= 1
    return None


def _exemption_for(lines: list[str], number: int, content: str = "") -> str | None:
    """The declared reason for the finding on line ``number``, or None.

    TWO ANCHOR POINTS, both of which had to be learned by using the mechanism:

    * the finding's own line and the CONTIGUOUS comment block above it. A reason worth
      reading is longer than a trailing comment can hold at this repo's 100-column limit,
      so black moves it onto its own line -- a first cut that checked only one line above
      silently ignored a three-line reason I had just written. A rule whose escape hatch
      depends on the formatter's line-breaking fails at random.
    * the STATEMENT containing the finding. A finding inside a multi-line literal has no
      line a comment can attach to, so the first cut ignored a declaration on a
      triple-quoted test fixture. The easy way out was to exempt the whole file on a
      path list, which would have papered over a gap in this mechanism with a blanket
      exclusion.
    * for a NON-PYTHON file, the indented block's owning line, which is the same problem
      again: a finding inside a YAML ``>`` or ``|`` scalar cannot carry a ``#``, because
      that would become part of the string. Solving it only for Python left two real
      template files unexemptable.

    A declaration above a large container covers findings anywhere inside it. That
    over-reach is accepted knowingly and is the same trade made for a large Python
    statement: the declaration is explicit, in the diff, and carries a reason.
    """
    direct = _contiguous_comment_reason(lines, number - 1)
    if direct is not None:
        return direct
    start = _statement_start(content, number) if content else None
    if start is None:
        # Not Python, or unparseable: fall back to the indentation-based container.
        start = _container_start(lines, number)
    if start is not None and start != number:
        return _contiguous_comment_reason(lines, start - 1)
    return None


def _container_start(lines: list[str], number: int) -> int | None:
    """The line owning the indented block that contains line ``number``, 1-based.

    THE YAML HALF OF THE SAME PROBLEM the statement anchor solved for Python. A finding
    inside a ``>`` or ``|`` block scalar has no line a comment can attach to: a ``#`` there
    becomes part of the string, so a declaration written next to it would change the data
    and exempt nothing. The owning key is the nearest preceding line indented LESS than the
    finding, and a declaration above that key is where a reader would look.
    """
    index = number - 1
    if not 0 <= index < len(lines):
        return None
    target = len(lines[index]) - len(lines[index].lstrip())
    for cursor in range(index - 1, -1, -1):
        line = lines[cursor]
        if not line.strip():
            continue
        if len(line) - len(line.lstrip()) < target:
            return cursor + 1
    return None


def offenders_in_text(content: str, rel: str) -> list[dict]:
    """Findings for one file's TEXT.

    Public so tests can call it with constructed input -- a multi-line call, an exempted
    line, a shrug of a reason -- rather than editing a real file. Mutating a real input
    tests the input; it does not test the checker.
    """
    lines = content.splitlines()
    offenders: list[dict] = []
    for number, label, detail in findings_with_lines(content, rel):
        exemption = _exemption_for(lines, number, content)
        if exemption is not None and len(exemption) >= _MIN_REASON_CHARS:
            continue
        if exemption is not None:
            offenders.append(
                {
                    "file": rel,
                    "line": number,
                    "label": label,
                    "message": (
                        f"{label} at {rel}:{number} is exempted with no usable reason"
                        f" ({exemption!r}). Say what makes it safe here, in at least"
                        f" {_MIN_REASON_CHARS} characters, so the next reader can judge"
                        " it. An escape hatch without that becomes the norm."
                    ),
                }
            )
            continue
        offenders.append(
            {
                "file": rel,
                "line": number,
                "label": label,
                "detail": detail,
                "message": (
                    f"{label} in {detail} at {rel}:{number}. A live shell injection sat"
                    " behind exactly this pattern for a month while the old detector"
                    " reported clean, because its regex could not cross a newline"
                    " (WO 26675b56). If it is genuinely safe here, say so on that line:"
                    " '# security-scan: <why>'."
                ),
            }
        )
    return offenders


def _offenders_in(rel: str) -> list[dict]:
    try:
        content = (REPO_ROOT / rel).read_text(encoding="utf-8")
    except OSError:
        return []
    return offenders_in_text(content, rel)


def run(base_ref: str | None = None) -> dict:
    """Scan the files this change set touches."""
    files = changed_scannable_files(base_ref)
    offenders: list[dict] = []
    for rel in files:
        offenders.extend(_offenders_in(rel))
    return {
        "status": "fail" if offenders else "pass",
        "files_checked": files,
        "offenders": offenders,
    }


def main() -> int:
    result = run()
    if result["status"] != "pass":
        print(json.dumps(result, indent=2, sort_keys=True))
        print(
            f"\nsecurity-scan: FAILED - {len(result['offenders'])} finding(s) in changed" " files.",
            file=sys.stderr,
        )
        return 1
    checked = result["files_checked"]
    if not checked:
        print("security-scan: OK - no scannable file changed.")
    else:
        print(f"security-scan: OK - {len(checked)} changed file(s), no findings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
