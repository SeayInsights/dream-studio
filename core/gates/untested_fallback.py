"""Gate: a fallback lane must be entered by some test.

REVIEW LANE ``an-untested-fallback-lane`` (canonical/review_lanes.yml).

THE FINDING THIS COMES FROM. The Machinist on gw#858. ``fallback_lock`` and
``_pending_queue_thread_lock`` had zero test hits -- every ack test ran the flock path. The
Windows lane the docstring promised was unexercised. His signature phrasing: the test that
validates the fix cannot run on the platform the fallback exists for.

A fallback exists precisely BECAUSE the primary path can be unavailable. So the only
condition under which it ever runs is the one nobody develops in, which makes it the code
most likely to be wrong and least likely to be noticed. "It is there" and "it works" are
different claims, and a test is the only thing that separates them.

WHY DIFF-SCOPED. Measured 10 standing candidates across 944 product files in this repo.
Failing the whole tree would make this a wall on day one and get it switched off; scoping to
the change set stops the next one and drains the backlog as those files are touched -- the
ratchet ``normative-baseline`` and ``workflow-node-verification`` already use.

WHAT COUNTS AS "ENTERED BY A TEST" IS A TEXTUAL MENTION, and it is weaker than a first
reading suggests. Not just an import: ANY substring anywhere under tests/ clears the symbol,
including a comment -- "# someday we should test fallback_lock properly" is enough. An audit
had to point that out, because the docstring said "merely imports" and implied a reference
that at least resolves.

It stays the weak version deliberately: the strong one needs per-branch coverage data this
repo does not collect, and the weak one already catches the gw#858 shape, which was zero
mentions of any kind. But the honest statement is that this lane proves a name is KNOWN to
the tests, not that any test enters the branch.

WHAT A PLATFORM LANE CAN STILL HIDE BEHIND, measured by an audit rather than guessed at:
a DICT DISPATCH keyed by `platform.system()` has no `if` node at all and is invisible; and
a platform predicate under an abstracted name -- `requires_alternate_locking_strategy()`
rather than `running_on_windows()` -- misses the condition vocabulary, which is a fixed set
of literal tokens. Both are real. `def`/`class` definitions and assigned implementations
inside a recognised platform branch are covered, which is the shape gw#858 actually had.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: A name that says "this exists because the primary path was unavailable".
_FALLBACK_NAME = re.compile(r"fallback|legacy_|_legacy|_shim|degraded", re.IGNORECASE)

#: Handlers under which a definition is a fallback by construction, whatever it is called.
_FALLBACK_HANDLERS = (
    "ImportError",
    "ModuleNotFoundError",
    "OSError",
    "NotImplementedError",
    "AttributeError",
)

#: A branch condition that means "this code exists for a platform the author is not on".
#:
#: ADDED AFTER AN AUDIT FOUND THE DETECTOR BLIND TO ITS OWN PRECEDENT. gw#858 was a WINDOWS
#: lane. Looking only at names and at exception handlers missed
#: `if platform.system() == "Windows": def windows_path_handler(...)` entirely -- a detector
#: for adam's finding that could not see the shape of adam's finding.
_PLATFORM_TEST = re.compile(
    r"platform\.|sys\.platform|os\.name|WINDOWS|POSIX|is_windows|_WIN\b|nt['\"]",
    re.IGNORECASE,
)

#: An author who knows a lane is unexercised and cannot fix that yet says so, with a reason.
_EXEMPTION = re.compile(r"#\s*untested-fallback:\s*(?P<reason>\S.*)")

_MIN_REASON_CHARS = 20


def _git(argv: list[str], repo_root: Path | None = None) -> list[str]:
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            argv,
            cwd=str(repo_root or REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    return [
        line.strip().replace("\\", "/") for line in (proc.stdout or "").splitlines() if line.strip()
    ]


def changed_python_files(base_ref: str | None = None, repo_root: Path | None = None) -> list[str]:
    """Product ``.py`` files this change set touches, staged, committed or untracked.

    Untracked included: ``git diff`` never reports one, and a brand-new module is exactly
    where a brand-new fallback arrives.
    """
    base = base_ref or os.environ.get("DREAM_STUDIO_BASE_REF") or "origin/main"
    paths: set[str] = set()
    for argv in (
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        ["git", "diff", "--name-only", "--cached"],
        ["git", "diff", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        for name in _git(argv, repo_root):
            if name.endswith(".py") and not name.startswith("tests/"):
                paths.add(name)
    root = repo_root or REPO_ROOT
    return sorted(p for p in paths if (root / p).is_file())


def _test_corpus(repo_root: Path | None = None) -> str:
    """Every test file's text, concatenated. Read once; this is the expensive part.

    UNTRACKED TESTS COUNT. A first cut listed only tracked files and the gate then reported
    its own `fallback_symbols` as untested while the brand-new test file importing it sat
    unstaged -- the same untracked blind spot handled on the product side two functions
    above and missed here. A test written in the same change as the fallback is the normal
    case, not the exception.
    """
    blob: list[str] = []
    tracked = _git(["git", "ls-files", "tests/**/*.py"], repo_root) + _git(
        ["git", "ls-files", "tests/*.py"], repo_root
    )
    untracked = [
        name
        for name in _git(["git", "ls-files", "--others", "--exclude-standard"], repo_root)
        if name.startswith("tests/") and name.endswith(".py")
    ]
    for rel in dict.fromkeys(tracked + untracked):
        try:
            blob.append(((repo_root or REPO_ROOT) / rel).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
    return "\n".join(blob)


def fallback_symbols(source: str) -> list[tuple[str, int, str]]:
    """``(name, line, why_it_is_a_fallback)`` for one module's text.

    Public so tests can call it with constructed source rather than editing a real module.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []

    found: list[tuple[str, int, str]] = []
    definitions = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

    for node in ast.walk(tree):
        if isinstance(node, definitions) and _FALLBACK_NAME.search(node.name):
            found.append((node.name, node.lineno, "its name says it is a fallback"))
        if isinstance(node, ast.Try):
            for handler in node.handlers:
                caught = ast.unparse(handler.type) if handler.type is not None else ""
                if not any(name in caught for name in _FALLBACK_HANDLERS):
                    continue
                for child in ast.walk(handler):
                    if isinstance(child, definitions):
                        found.append(
                            (
                                child.name,
                                child.lineno,
                                f"it is defined inside an `except {caught}` handler",
                            )
                        )
        if isinstance(node, ast.If):
            condition = ast.unparse(node.test)
            if not _PLATFORM_TEST.search(condition):
                continue
            # BOTH branches. Whichever side the author is not developing on is the lane
            # nobody enters, and which side that is depends on who is running the tests.
            for branch in (node.body, node.orelse):
                for statement in branch:
                    for child in ast.walk(statement):
                        if isinstance(child, definitions):
                            found.append(
                                (
                                    child.name,
                                    child.lineno,
                                    "it is defined inside a platform branch"
                                    f" (`{condition[:60]}`)",
                                )
                            )
                        # AN IMPLEMENTATION SWAPPED BY ASSIGNMENT is the same lane without
                        # a `def`. An audit found `acquire_lock = functools.partial(...)`
                        # and `impl = _win_lock_impl` evading this entirely, and both are
                        # ordinary ways to write a platform shim in Python. A CONSTANT is
                        # not a lane -- `SEP = "\\"` needs no test -- so only a value that
                        # names or builds something callable counts.
                        if isinstance(child, ast.Assign) and isinstance(
                            child.value, (ast.Call, ast.Name, ast.Attribute, ast.Lambda)
                        ):
                            for target in child.targets:
                                if isinstance(target, ast.Name):
                                    found.append(
                                        (
                                            target.id,
                                            child.lineno,
                                            "an implementation is assigned to it inside a"
                                            f" platform branch (`{condition[:60]}`)",
                                        )
                                    )
    # One name reported once, at its first definition.
    unique: dict[str, tuple[str, int, str]] = {}
    for name, line, why in sorted(found, key=lambda item: item[1]):
        unique.setdefault(name, (name, line, why))
    return list(unique.values())


def offenders_in_text(source: str, rel: str, test_corpus: str) -> list[dict]:
    """Findings for one module, given the text of every test."""
    lines = source.splitlines()
    offenders: list[dict] = []
    for name, line, why in fallback_symbols(source):
        if re.search(rf"\b{re.escape(name)}\b", test_corpus):
            continue
        reason = _declared_reason(lines, line)
        if reason is not None and len(reason) >= _MIN_REASON_CHARS:
            continue
        if reason is not None:
            offenders.append(
                {
                    "file": rel,
                    "line": line,
                    "symbol": name,
                    "message": (
                        f"{rel}:{line} {name!r} is exempted with no usable reason"
                        f" ({reason!r}). Say why the lane cannot be entered by a test, in"
                        f" at least {_MIN_REASON_CHARS} characters."
                    ),
                }
            )
            continue
        offenders.append(
            {
                "file": rel,
                "line": line,
                "symbol": name,
                "message": (
                    f"{rel}:{line} {name!r} is a fallback ({why}) and no test mentions it"
                    " anywhere. A fallback runs only when the primary path is unavailable,"
                    " which is the condition nobody develops in -- so it is the code most"
                    " likely to be wrong and least likely to be noticed. That is gw#858:"
                    " `fallback_lock` had zero test hits while every ack test ran the flock"
                    " path, so the test validating the fix could not run on the platform"
                    " the fallback existed for. Enter it from a test, or say why it cannot"
                    " be: '# untested-fallback: <why>'."
                ),
            }
        )
    return offenders


def _declared_reason(lines: list[str], definition_line: int) -> str | None:
    """A declaration on the definition's line or the contiguous comment block above it."""
    index = definition_line - 1
    if 0 <= index < len(lines):
        match = _EXEMPTION.search(lines[index])
        if match:
            return match.group("reason").strip()
    cursor = index - 1
    while 0 <= cursor < len(lines) and lines[cursor].lstrip().startswith(("#", "@")):
        match = _EXEMPTION.search(lines[cursor])
        if match:
            return match.group("reason").strip()
        cursor -= 1
    return None


def run(base_ref: str | None = None, repo_root: Path | None = None) -> dict:
    changed = changed_python_files(base_ref, repo_root)
    if not changed:
        return {"status": "pass", "files_checked": [], "offenders": []}
    corpus = _test_corpus(repo_root)
    offenders: list[dict] = []
    for rel in changed:
        try:
            source = ((repo_root or REPO_ROOT) / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        offenders.extend(offenders_in_text(source, rel, corpus))
    return {
        "status": "fail" if offenders else "pass",
        "files_checked": changed,
        "offenders": offenders,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report a fallback lane no test enters.")
    parser.add_argument(
        "--repo-root",
        default=None,
        help=(
            "Review THIS tree instead of the one this gate lives in. The round table"
            " appends it when convening against another project; without it the gate"
            " scans its own install, which would report another project's result as"
            " clean."
        ),
    )
    args = parser.parse_args(argv)
    root = Path(args.repo_root) if args.repo_root else None

    result = run(None, root)
    if result["status"] != "pass":
        print(json.dumps(result, indent=2, sort_keys=True))
        print(
            f"\nuntested-fallback: FAILED - {len(result['offenders'])} fallback lane(s) no"
            " test enters.",
            file=sys.stderr,
        )
        return 1
    checked = result["files_checked"]
    if not checked:
        print("untested-fallback: OK - no product module changed.")
    else:
        print(
            f"untested-fallback: OK - {len(checked)} changed module(s), every fallback lane"
            " is referenced by a test or declared."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
