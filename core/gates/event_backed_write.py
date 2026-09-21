"""If this record were rebuilt from its events tomorrow, would it still be here?

THE LANE `a-write-no-event-can-reconstruct` DECLARED THIS DETECTOR AND NOBODY
WROTE IT. Five sites in `interfaces/cli/commands/prove.py` already carry
`# event-backed-write:` exemption comments and a test docstring in
tests/unit/test_gap_fanout.py reasons about "what `event-backed-write` reports" --
so the convention was established and written against while
`py -m core.gates.event_backed_write` was a ModuleNotFoundError. The registry
gate refuses a lane whose detector does not import; nothing ran the registry gate.

THE DEFECT. A row written straight into a projection table with no canonical
event beside it. Nothing fails and the row reads as durable, because the
projection is a real table and the write really happened -- but `pre_rebuild`
TRUNCATES that table before replaying events, so a rebuild cannot reconstruct
what no event describes. The row does not become corrupt; it silently ceases to
exist. It usually arrives by copying a sibling write site rather than the
designated writer.

THE TARGET TABLES ARE DERIVED, NOT LISTED. Each projection declares its own
`target_tables` -- the set `pre_rebuild` truncates, which is the actual blast
radius. Hardcoding the tables the defect was first found in would exempt the
rest, which is the same subset-of-what-it-writes shape this gate exists to
catch. Derivation is static (AST over core/projections/), because building a
live ProjectionRegistry calls setup_tables() inside a transaction and a gate
must not write to the operator's authority to decide whether to complain.

SCOPE: TESTS ARE OUT. A fixture building rows directly is what a fixture IS.
Including them measured 214 INSERT sites against 4 real ones, and a gate that
reports 210 things nobody should change is a wall.

ADVISORY. It exits non-zero so the review lane reports the finding, but it is
deliberately not wired into pre-push as blocking while a known genuine finding
is outstanding: a blocking gate that ships red teaches people to bypass it.

WHAT IT DOES NOT DECIDE (the lane's `defers`):
  - a bare UPDATE that changes a projected row's state -- this matches INSERT
    INTO and INSERT OR REPLACE INTO only (WO 4fbe3282)
  - whether replaying the emitted event actually REPRODUCES the row. This proves
    an event is emitted beside the write, not that its payload rebuilds it.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Directories that never hold a designated writer.
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

#: A call whose name matches this is an event emission.
_EMIT_RE = re.compile(r"(^|_)emit|write_event")

#: The site-level declaration that exempts a write. Already in use in prove.py.
_EXEMPT_MARKER = "event-backed-write:"


def _projection_tables(root: Path) -> list[str]:
    """Every table some projection declares as its own, read statically.

    Resolves `target_tables = [_TABLE]` against the module-level constant, which
    is how all six projections here spell it. A declaration this cannot resolve
    is skipped rather than guessed -- a wrong table name would silently narrow
    the scan, and a scan that narrows to nothing reports clean.
    """
    tables: set[str] = set()
    proj_dir = root / "core" / "projections"
    if not proj_dir.is_dir():
        return []
    for path in sorted(proj_dir.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        consts: dict[str, str] = {}
        for node in tree.body:
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        consts[tgt.id] = node.value.value
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            names = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if "target_tables" not in names:
                continue
            if not isinstance(node.value, (ast.List, ast.Tuple)):
                continue
            for elt in node.value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    tables.add(elt.value)
                elif isinstance(elt, ast.Name) and elt.id in consts:
                    tables.add(consts[elt.id])
    return sorted(tables)


def _product_files(root: Path) -> list[Path]:
    out = []
    for path in root.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in path.relative_to(root).parts[:-1]):
            continue
        if path.relative_to(root).parts[0] in _SKIP_DIRS:
            continue
        out.append(path)
    return sorted(out)


def _insert_re(tables: list[str]) -> re.Pattern:
    alt = "|".join(re.escape(t) for t in tables)
    return re.compile(rf"INSERT\s+(?:OR\s+REPLACE\s+)?INTO\s+({alt})\b", re.IGNORECASE)


def _emits(func: ast.AST) -> bool:
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        name = ""
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
        if name and _EMIT_RE.search(name):
            return True
    return False


def _scan_file(path: Path, rel: str, pattern: re.Pattern) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not pattern.search(text):
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    lines = text.splitlines()
    findings = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        hits = []
        for node in ast.walk(func):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                m = pattern.search(node.value)
                if m:
                    hits.append((getattr(node, "lineno", func.lineno), m.group(1)))
        if not hits:
            continue
        if _emits(func):
            continue
        # The marker is a COMMENT, which the AST discards -- so it is read off the
        # source lines the function spans. A write may be deliberate; what is not
        # allowed is for it to be silent.
        start = func.lineno - 1
        end = max(getattr(func, "end_lineno", func.lineno), func.lineno)
        if any(_EXEMPT_MARKER in line for line in lines[start:end]):
            continue
        line, table = hits[0]
        findings.append({"file": rel, "line": line, "function": func.name, "table": table})
    return findings


def run(root: Path | None = None) -> dict:
    root = Path(root) if root else REPO_ROOT
    tables = _projection_tables(root)
    if not tables:
        # NOT CLEAN. No resolvable projection means this gate scanned for nothing,
        # and reporting that as a pass is the compared-nothing-reported-clean shape
        # the lane exists to refuse.
        return {
            "status": "unknown",
            "reason": "no projection declared a resolvable target_tables under core/projections/",
            "tables": [],
            "findings": [],
        }
    pattern = _insert_re(tables)
    findings: list[dict] = []
    for path in _product_files(root):
        findings.extend(_scan_file(path, path.relative_to(root).as_posix(), pattern))
    findings.sort(key=lambda f: (f["file"], f["line"]))
    return {
        "status": "found" if findings else "clean",
        "tables": tables,
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report rows written into a projection table with no event to rebuild them from."
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
        print(f"event-backed-write: UNKNOWN - {result['reason']}")
        return 0
    if result["status"] == "found":
        print(json.dumps(result, indent=2, sort_keys=True))
        print(
            f"\nevent-backed-write: {len(result['findings'])} write(s) into a projection"
            " table with no event beside them. pre_rebuild truncates these tables before"
            " replay, so a rebuild drops the row. Emit a canonical event at the write, or"
            f" mark the site `# {_EXEMPT_MARKER} <why>` if the row is deliberately"
            " disposable.",
            file=sys.stderr,
        )
        return 1
    print(
        f"event-backed-write: OK - every write into {len(result['tables'])} projection"
        " table(s) emits an event or declares why it does not."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
