"""This wait is bounded per item. How many items can there be, and what bounds the total?

THE LANE `a-per-item-wait-with-no-aggregate-deadline` DECLARED THIS DETECTOR AND
NOBODY WROTE IT. `py -m core.gates.aggregate_deadline` was a ModuleNotFoundError
while the lane read as mechanically enforced.

THE DEFECT. A module that already solved unbounded stall for one loop grows a
per-item retry in another, with no aggregate deadline. Each item waits a bounded
amount, so every wait looks correct in isolation -- and the ceiling then
multiplies by a data-dependent count and passes the very timeout the module
itself cites. Nobody wrote an unbounded wait; the unboundedness is in the
multiplication.

THE SHAPE IS NESTING, AND THE SHARPENING CAME FROM A FALSE POSITIVE. The first
cut -- a sleep in a loop, in a module that defines a budget constant -- found one
candidate, `core/work_orders/artifacts.py:216`, and reading it showed
`_LOCK_ATTEMPTS = 4` with a 0.15s backoff: 0.90s worst case, not inside any outer
per-item loop. Bounded, and not the finding. Requiring NESTING -- a sleeping loop
inside another loop, with neither consulting a deadline -- drops this tree to
zero, which is why this one runs whole-tree rather than diff-scoped. A gate that
fires on a bounded retry teaches people that its findings are noise.

WHAT COUNTS AS CONSULTING A DEADLINE. Any reference, in either loop's test or
body, to a name that reads as a clock budget (deadline, budget, expires, until,
timeout, elapsed) or to a monotonic clock read. This is deliberately generous:
the lane asks whether anything bounds the total, and a loop that mentions its
budget at all is a loop someone thought about. A false negative here costs a
missed finding; a false positive costs the gate's credibility.

WHAT IT DOES NOT DECIDE (the lane's `defers`):
  - multiplication through a CALL. A loop whose helper sleeps in its own loop is
    the same defect and needs a call graph to see. This matches lexical nesting
    only.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_SKIP_DIRS = frozenset(
    {
        "tests",
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        "build",
        "dist",
        ".claude",
    }
)

_LOOP = (ast.For, ast.AsyncFor, ast.While)

#: A name mentioning any of these reads as a clock budget.
_BUDGET_WORDS = ("deadline", "budget", "expire", "until", "timeout", "elapsed")

#: Reading one of these is reading a clock.
_CLOCK_FUNCS = ("monotonic", "perf_counter", "time", "now")

_SLEEP_FUNCS = ("sleep",)

#: The site-level declaration that exempts a nest whose total really is bounded.
_EXEMPT_MARKER = "aggregate-deadline:"


def _call_names(node: ast.AST) -> list[str]:
    names = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            if isinstance(sub.func, ast.Name):
                names.append(sub.func.id)
            elif isinstance(sub.func, ast.Attribute):
                names.append(sub.func.attr)
    return names


def _sleeps(node: ast.AST) -> bool:
    return any(n in _SLEEP_FUNCS for n in _call_names(node))


def _consults_a_deadline(loop: ast.AST) -> bool:
    """Does this loop reference a clock budget anywhere in its test or body?

    Generous on purpose. The lane asks whether ANYTHING bounds the total, and a
    loop that names its budget is a loop somebody reasoned about. Being strict
    here would report bounded retries, which is exactly the false positive that
    forced this detector's shape in the first place.
    """
    for sub in ast.walk(loop):
        if isinstance(sub, ast.Name) and any(w in sub.id.lower() for w in _BUDGET_WORDS):
            return True
        if isinstance(sub, ast.Attribute) and any(w in sub.attr.lower() for w in _BUDGET_WORDS):
            return True
        if isinstance(sub, ast.Call):
            fname = ""
            if isinstance(sub.func, ast.Name):
                fname = sub.func.id
            elif isinstance(sub.func, ast.Attribute):
                fname = sub.func.attr
            if fname in _CLOCK_FUNCS and fname not in _SLEEP_FUNCS:
                return True
    return False


def _inner_loops(outer: ast.AST) -> list[ast.AST]:
    """Loops lexically inside *outer*, excluding outer itself."""
    found = []
    for sub in ast.walk(outer):
        if sub is outer:
            continue
        if isinstance(sub, _LOOP):
            found.append(sub)
    return found


def _scan_file(path: Path, rel: str) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if "sleep" not in text:
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    lines = text.splitlines()
    # THE MARKER'S SCOPE IS THE ENCLOSING FUNCTION, not the loop. The convention
    # puts it on the line above the loop it explains, which is outside the loop's
    # own span -- checking only the span silently ignored every declaration
    # written the natural way. Module-level loops fall back to their own span.
    func_spans = [
        (f.lineno, getattr(f, "end_lineno", f.lineno))
        for f in ast.walk(tree)
        if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]

    def _declared(loop: ast.AST) -> bool:
        lo = loop.lineno
        hi = max(getattr(loop, "end_lineno", lo), lo)
        for fstart, fend in func_spans:
            if fstart <= lo and hi <= fend:
                lo, hi = fstart, fend
                break
        # Bound to a name rather than written inline: black spaces a slice whose
        # bound is an expression (`lines[lo - 1 : hi]`) and flake8 then reports
        # E203 on the space it just inserted.
        first = lo - 1
        return any(_EXEMPT_MARKER in line for line in lines[first:hi])

    findings = []
    for outer in ast.walk(tree):
        if not isinstance(outer, _LOOP):
            continue
        if _consults_a_deadline(outer):
            continue
        for inner in _inner_loops(outer):
            if not _sleeps(inner):
                continue
            if _consults_a_deadline(inner):
                continue
            if _declared(outer):
                continue
            findings.append(
                {
                    "file": rel,
                    "outer_loop_line": outer.lineno,
                    "sleeping_loop_line": inner.lineno,
                }
            )
    return findings


def _product_files(root: Path) -> list[Path]:
    out = []
    for path in root.rglob("*.py"):
        parts = path.relative_to(root).parts
        if any(part in _SKIP_DIRS for part in parts[:-1]) or parts[0] in _SKIP_DIRS:
            continue
        out.append(path)
    return sorted(out)


def run(root: Path | None = None) -> dict:
    root = Path(root) if root else REPO_ROOT
    files = _product_files(root)
    if not files:
        # A scan with nothing to scan is not a clean scan.
        return {"status": "unknown", "reason": "no product Python files found", "findings": []}
    findings: list[dict] = []
    for path in files:
        findings.extend(_scan_file(path, path.relative_to(root).as_posix()))
    findings.sort(key=lambda f: (f["file"], f["outer_loop_line"]))
    return {
        "status": "found" if findings else "clean",
        "files_scanned": len(files),
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report a sleeping loop nested in another loop where nothing bounds the total wait."
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
    args = parser.parse_args(argv)
    result = run(Path(args.repo_root) if args.repo_root else None)

    if result["status"] == "unknown":
        print(f"aggregate-deadline: UNKNOWN - {result['reason']}")
        return 0
    if result["status"] == "found":
        print(json.dumps(result, indent=2, sort_keys=True))
        print(
            f"\naggregate-deadline: {len(result['findings'])} nested wait(s) with no"
            " aggregate bound. Each iteration is bounded; the total is not, and it"
            " multiplies by a count the data decides. Give the outer loop a deadline, or"
            f" mark the site `# {_EXEMPT_MARKER} <why the total is bounded>`.",
            file=sys.stderr,
        )
        return 1
    print(
        f"aggregate-deadline: OK - {result['files_scanned']} file(s), no sleeping loop"
        " nested inside an unbounded loop."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
