"""This fallback exists because the primary path can be unavailable. Does any test enter it?

THE LANE `an-untested-fallback-lane` DECLARED THIS DETECTOR AND NOBODY WROTE IT.
`py -m core.gates.untested_fallback` was a ModuleNotFoundError while the lane
read as mechanically enforced.

THE DEFECT. A platform or exception fallback whose tests all run the other
branch -- so the test that validates the fix cannot run on the platform the
fallback exists for. The suite is green, the fallback has never executed, and the
first time it does is in front of a user on the platform nobody tested.

PLATFORM CONDITIONALS COUNT, AND MISSING THEM WAS THE ORIGINAL BLIND SPOT.
Name-and-handler detection alone measured 10 candidates across 944 product files;
including platform-conditional branches raised it to 14. The lane's own precedent
was a Windows-only path, so a detector blind to platform conditionals could not
see the shape of the case it was written from.

NOT EVERY `except` IS A FALLBACK, and treating them alike is what made the first
cut of this detector useless: it reported 685 sites whole-tree against the lane's
14. Most handlers are error handling -- log it, return None, carry on -- and take
no alternative path at all. A fallback is a handler that catches the primary path
being UNAVAILABLE (ImportError, ModuleNotFoundError) and then PROVIDES the thing
another way, by importing or assigning in its body. That pair, plus platform
conditionals, measures 7 here: findable, fixable, and the right order of
magnitude. A gate reporting 685 is a wall, and a wall gets switched off.

DIFF-SCOPED. The standing candidates would be a wall on day one, and a gate that
fires on hundreds of pre-existing sites is a gate someone turns off in its first
week. Scoping to the change set drains the backlog as those files are touched --
the same ratchet `normative-baseline` and `workflow-node-verification` use.

WHAT IT DOES NOT DECIDE (the lane's `defers`):
  - whether any test actually ENTERS the branch. Any textual mention of the
    symbol anywhere under tests/, a comment included, clears it. This proves a
    name is KNOWN to the tests, not that it is exercised by them. Proving entry
    needs coverage data, which this does not read.
  - a platform dispatch written as a dict keyed on platform.system(), which has
    no `if` node to find, and a platform predicate hidden behind an abstracted
    name.
  - fallbacks in files outside the change set.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_SKIP_DIRS = frozenset(
    {"tests", ".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist", ".claude"}
)

#: Catching one of these means the primary path may simply not be there.
_UNAVAILABLE_ERRORS = ("ImportError", "ModuleNotFoundError")

#: Reading one of these is asking which platform we are on.
_PLATFORM_TOKENS = ("platform.system", "sys.platform", "os.name", "platform.machine")

#: The site-level declaration that exempts a fallback nothing will ever test.
_EXEMPT_MARKER = "untested-fallback:"


def _test_corpus(root: Path) -> str:
    """Everything under tests/, concatenated once.

    A textual mention is all the lane asks for -- see the module docstring on
    what this deliberately does not prove.
    """
    tests = root / "tests"
    if not tests.is_dir():
        return ""
    parts = []
    for path in tests.rglob("*.py"):
        parts.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def _is_platform_test(node: ast.AST) -> bool:
    try:
        src = ast.unparse(node)
    except Exception:  # noqa: BLE001 - unparse is best-effort on odd nodes
        return False
    return any(tok in src for tok in _PLATFORM_TOKENS)


def _is_fallback_handler(handler: ast.ExceptHandler) -> bool:
    """Does this handler catch the primary path being UNAVAILABLE and supply it another way?

    Two conditions, and both matter. Without the first, ordinary error handling
    counts. Without the second, a handler that merely logs and returns counts.
    Requiring neither reported 685 sites against the lane's 14 -- which is a wall,
    not a gate.
    """
    if handler.type is None:
        return False  # a bare except is not specifically "primary path unavailable"
    try:
        caught = ast.unparse(handler.type)
    except Exception:  # noqa: BLE001 - unparse is best-effort on odd nodes
        return False
    if not any(exc in caught for exc in _UNAVAILABLE_ERRORS):
        return False
    # Supplies the value another way rather than just recording the failure.
    return any(isinstance(n, (ast.Import, ast.ImportFrom, ast.Assign)) for n in handler.body)


def _enclosing_functions(tree: ast.AST) -> list[tuple[int, int, str]]:
    return sorted(
        (
            (f.lineno, getattr(f, "end_lineno", f.lineno), f.name)
            for f in ast.walk(tree)
            if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))
        ),
        key=lambda t: t[1] - t[0],
    )


def _scan_file(text: str, rel: str, corpus: str) -> list[dict]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    lines = text.splitlines()
    funcs = _enclosing_functions(tree)

    def _owner(line: int) -> tuple[str, int, int] | None:
        for start, end, name in funcs:  # innermost first
            if start <= line <= end:
                return name, start, end
        return None

    findings = []
    seen: set[tuple[str, int]] = set()
    candidates: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and _is_fallback_handler(node):
            candidates.append((node.lineno, "exception"))
        elif isinstance(node, ast.If) and _is_platform_test(node.test):
            candidates.append((node.lineno, "platform"))

    for line, kind in candidates:
        owner = _owner(line)
        if owner is None:
            continue  # module-level fallback has no symbol a test could name
        name, start, end = owner
        if name.startswith("__") or len(name) <= 2:
            continue  # too generic for a textual mention to mean anything
        first = start - 1  # inline `start - 1 : end` gets spaced by black, then E203 by flake8
        if any(_EXEMPT_MARKER in ln for ln in lines[first:end]):
            continue
        if name in corpus:
            continue
        key = (name, line)
        if key in seen:
            continue
        seen.add(key)
        findings.append({"file": rel, "line": line, "function": name, "kind": kind})
    return findings


def _changed_product_files(root: Path, all_files: bool) -> list[Path]:
    if all_files:
        out = []
        for path in root.rglob("*.py"):
            parts = path.relative_to(root).parts
            if any(p in _SKIP_DIRS for p in parts[:-1]) or parts[0] in _SKIP_DIRS:
                continue
            out.append(path)
        return sorted(out)

    from core.gates.round_table import changed_paths

    out = []
    for rel in changed_paths(root):
        if not rel.endswith(".py"):
            continue
        parts = Path(rel).parts
        if any(p in _SKIP_DIRS for p in parts[:-1]) or parts[0] in _SKIP_DIRS:
            continue
        path = root / rel
        if path.is_file():
            out.append(path)
    return sorted(out)


def run(root: Path | None = None, all_files: bool = False) -> dict:
    root = Path(root) if root else REPO_ROOT
    files = _changed_product_files(root, all_files)
    corpus = _test_corpus(root)
    findings: list[dict] = []
    for path in files:
        findings.extend(
            _scan_file(
                path.read_text(encoding="utf-8", errors="replace"),
                path.relative_to(root).as_posix(),
                corpus,
            )
        )
    findings.sort(key=lambda f: (f["file"], f["line"]))
    return {
        "status": "found" if findings else "clean",
        "scope": "whole-tree" if all_files else "change-set",
        "files_scanned": len(files),
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report a platform or exception fallback no test so much as names."
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help=(
            "Scan THIS tree instead of the one this gate lives in. The round table"
            " appends it when convening against another project; without it the gate"
            " scans its own install and reports that as the other project's result."
        ),
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help=(
            "Scan the whole tree rather than the change set. Shows the standing"
            " backlog; not the mode the gate runs in, because that backlog is a wall."
        ),
    )
    args = parser.parse_args(argv)
    result = run(Path(args.repo_root) if args.repo_root else None, args.all)

    if result["status"] == "found":
        print(json.dumps(result, indent=2, sort_keys=True))
        print(
            f"\nuntested-fallback: {len(result['findings'])} fallback(s) in the"
            f" {result['scope']} that no test even names. The primary path is what the"
            " suite exercises, so the branch that exists for the unavailable case has"
            f" never run. Add a test, or mark the site `# {_EXEMPT_MARKER} <why>`.",
            file=sys.stderr,
        )
        return 1
    print(
        f"untested-fallback: OK - {result['files_scanned']} file(s) in the"
        f" {result['scope']}, every fallback is named by some test."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
