"""Dependency rule gates — grep-level enforcement of layer boundary rules.

Rules are documented in docs/reference/layer-map.md.

Rule 1: Adapters never write to authority tables. runtime/hooks/ emits via spool only.
Rule 2: Projections are read-only. No INSERT/UPDATE/DELETE from projections/ modules.
Rule 3: CLI is the designated writer for business state (advisory tier — route handlers only).
Rule 4: The ingestor is the sole writer to canonical_events (the compat VIEW alias).

Usage:
    py -m core.gates.dependency_rules rule1   # adapters-no-authority (blocking)
    py -m core.gates.dependency_rules rule2   # projections-readonly (blocking)
    py -m core.gates.dependency_rules rule3   # cli-business-state-writer (advisory)
    py -m core.gates.dependency_rules rule4   # ingestor-sole-event-writer (blocking)
    py -m core.gates.dependency_rules         # run rules 1, 2, 4 (all blocking)

Exit 0 = pass. Exit 1 = violation(s) found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Matches SQL write statements against authority table name prefixes.
# Covers: INSERT [OR ...] INTO, UPDATE, DELETE FROM
# Table prefixes: business_*, raw_*, reg_*, canonical_events (compat VIEW)
_AUTHORITY_WRITE = re.compile(
    r"(?:INSERT\s+(?:OR\s+\w+\s+)?INTO|UPDATE|DELETE\s+FROM)\s+"
    r"(?:business_|raw_|reg_|canonical_events)\w*",
    re.IGNORECASE,
)

# Matches direct INSERT into canonical_events (the compat VIEW — must never be written).
_CANONICAL_EVENTS_INSERT = re.compile(
    r"INSERT\s+(?:OR\s+\w+\s+)?INTO\s+canonical_events\b",
    re.IGNORECASE,
)

# Matches SQL write statements against business_* tables only (for rule 3 advisory scope).
_BUSINESS_WRITE = re.compile(
    r"(?:INSERT\s+(?:OR\s+\w+\s+)?INTO|UPDATE|DELETE\s+FROM)\s+business_\w*",
    re.IGNORECASE,
)


def _py_files(directory: Path, exclude_subdirs: tuple[str, ...] = ()) -> list[Path]:
    files = []
    for p in directory.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        if exclude_subdirs and any(part in exclude_subdirs for part in p.parts):
            continue
        files.append(p)
    return files


def _scan_file(path: Path, pattern: re.Pattern) -> list[tuple[int, str]]:
    """Return (lineno, line) pairs where pattern matches, skipping comment-only lines."""
    matches = []
    for lineno, raw_line in enumerate(
        path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
    ):
        stripped = raw_line.strip()
        if stripped.startswith("#"):
            continue
        if pattern.search(raw_line):
            matches.append((lineno, stripped))
    return matches


def check_rule1(repo_root: Path = REPO_ROOT) -> list[tuple[Path, int, str]]:
    """Rule 1: runtime/ hooks must not write directly to authority tables.

    Allowed: spool writes through emitters (ingestor path). Read-only queries.
    Blocked: any direct INSERT/UPDATE/DELETE on business_*, raw_*, reg_*, canonical_events.
    """
    violations: list[tuple[Path, int, str]] = []
    runtime_dir = repo_root / "runtime"
    if not runtime_dir.exists():
        return violations
    for path in _py_files(runtime_dir):
        for lineno, line in _scan_file(path, _AUTHORITY_WRITE):
            violations.append((path, lineno, line))
    return violations


def check_rule2(repo_root: Path = REPO_ROOT) -> list[tuple[Path, int, str]]:
    """Rule 2: projections/ modules must not write to authority tables.

    Scans projections/api/ and projections/core/, excluding projections/tests/.
    Tests are allowed to INSERT fixture data; production route/collector code is not.
    """
    violations: list[tuple[Path, int, str]] = []
    for subdir in ("api", "core"):
        scan_dir = repo_root / "projections" / subdir
        if not scan_dir.exists():
            continue
        for path in _py_files(scan_dir, exclude_subdirs=("tests",)):
            for lineno, line in _scan_file(path, _AUTHORITY_WRITE):
                violations.append((path, lineno, line))
    return violations


def check_rule3(repo_root: Path = REPO_ROOT) -> list[tuple[Path, int, str]]:
    """Rule 3 (advisory): route handlers in projections/api/routes/ must not write business_*.

    This is a warning-tier gate — false-positive rate not yet confirmed low enough to block.
    The most clearly-wrong pattern is API route handlers writing business state tables directly,
    bypassing the CLI/work-order layer.
    """
    violations: list[tuple[Path, int, str]] = []
    routes_dir = repo_root / "projections" / "api" / "routes"
    if not routes_dir.exists():
        return violations
    for path in _py_files(routes_dir):
        for lineno, line in _scan_file(path, _BUSINESS_WRITE):
            violations.append((path, lineno, line))
    return violations


def check_rule4(repo_root: Path = REPO_ROOT) -> list[tuple[Path, int, str]]:
    """Rule 4: no module outside the ingestor path writes to canonical_events (the compat VIEW).

    canonical_events is a UNION VIEW over business_canonical_events and ai_canonical_events.
    Direct INSERTs to the VIEW alias are always wrong — the ingestor writes to the actual
    authority tables (business_canonical_events, ai_canonical_events) directly.

    Scans all .py files excluding tests/ and .planning/ directories.
    """
    violations: list[tuple[Path, int, str]] = []
    skip_dirs = frozenset({"tests", ".planning", "__pycache__"})
    for path in repo_root.rglob("*.py"):
        if any(part in skip_dirs for part in path.parts):
            continue
        for lineno, line in _scan_file(path, _CANONICAL_EVENTS_INSERT):
            violations.append((path, lineno, line))
    return violations


def _print_violations(rule_id: str, violations: list[tuple[Path, int, str]]) -> None:
    if not violations:
        print(f"{rule_id}: OK — no violations found")
        return
    print(f"{rule_id}: VIOLATIONS FOUND ({len(violations)})")
    for path, lineno, line in violations:
        try:
            rel = path.relative_to(REPO_ROOT)
        except ValueError:
            rel = path
        print(f"  {rel}:{lineno}: {line}")


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    rule = args[0].lower() if args else None

    dispatch = {
        "rule1": ("rule1-adapters-no-authority", check_rule1, False),
        "rule2": ("rule2-projections-readonly", check_rule2, False),
        "rule3": ("rule3-cli-business-state-writer", check_rule3, True),
        "rule4": ("rule4-ingestor-sole-event-writer", check_rule4, False),
    }

    if rule and rule not in dispatch:
        print(f"Unknown rule: {rule!r}. Choose from: {', '.join(dispatch)}", file=sys.stderr)
        return 1

    if rule:
        label, check_fn, is_advisory = dispatch[rule]
        violations = check_fn(REPO_ROOT)
        _print_violations(label, violations)
        if violations and not is_advisory:
            return 1
        return 0

    # Run all blocking rules when no rule specified.
    overall = 0
    for key in ("rule1", "rule2", "rule4"):
        label, check_fn, _ = dispatch[key]
        violations = check_fn(REPO_ROOT)
        _print_violations(label, violations)
        if violations:
            overall = 1
    return overall


if __name__ == "__main__":
    sys.exit(main())
