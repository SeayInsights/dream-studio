"""Test fixture dead-table resurrection guard.

Blocks `git push` when a test-file diff introduces CREATE TABLE for a table
that was permanently dropped by a numbered migration. Resurrecting a dead
table in a test fixture creates a DB state that can never exist in production
-- the real DB went through the DROP and has never had that table since.

The "dropped table ledger" is computed dynamically from migration files.
A table is "dead" if the last migration operation recorded against its name
was DROP TABLE (not CREATE TABLE or a RENAME TO target).

Exit codes:
  0 -- no dead-table resurrection found, or running in CI (GITHUB_ACTIONS=true)
  1 -- dead-table CREATE TABLE found in the test-file diff
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "core" / "event_store" / "migrations"

_TABLE_OP_RE = re.compile(
    r"(CREATE|DROP)\s+TABLE\s+(?:IF\s+(?:NOT\s+)?EXISTS\s+)?(\w+)",
    re.IGNORECASE,
)
_RENAME_TO_RE = re.compile(
    r"ALTER\s+TABLE\s+\w+\s+RENAME\s+TO\s+(\w+)",
    re.IGNORECASE,
)
_DIFF_CREATE_RE = re.compile(
    r"^\+[^+].*?CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)",
    re.IGNORECASE | re.MULTILINE,
)

# Suffixes used in rename-pattern intermediate tables (always transient)
_SKIP_SUFFIXES = ("_new", "_temp", "_backup")
_SKIP_INFIX_RE = re.compile(r"_bak\d+")


def _is_rename_intermediate(table: str) -> bool:
    t = table.lower()
    return any(t.endswith(s) for s in _SKIP_SUFFIXES) or bool(_SKIP_INFIX_RE.search(t))


def _migration_number(path: Path) -> int:
    try:
        return int(path.name.split("_")[0])
    except (ValueError, IndexError):
        return 0


def build_dead_table_ledger() -> frozenset[str]:
    """Return table names whose last migration operation was DROP TABLE.

    Processes migrations in number order. For each DROP TABLE or CREATE TABLE
    (and RENAME TO → treated as CREATE), records the last (op, num) per table
    name. Dead = last recorded op is DROP.
    """
    last_op: dict[str, tuple[str, int]] = {}

    for f in sorted(MIGRATIONS_DIR.glob("*.sql"), key=_migration_number):
        num = _migration_number(f)
        if num == 0:
            continue
        try:
            sql = f.read_text(encoding="utf-8")
        except OSError:
            continue

        for m in _TABLE_OP_RE.finditer(sql):
            op = m.group(1).upper()
            table = m.group(2).lower()
            if _is_rename_intermediate(table):
                continue
            prev_op, prev_num = last_op.get(table, ("", 0))
            if num > prev_num or num == prev_num:
                last_op[table] = (op, num)

        for m in _RENAME_TO_RE.finditer(sql):
            table = m.group(1).lower()
            if _is_rename_intermediate(table):
                continue
            prev_op, prev_num = last_op.get(table, ("", 0))
            if num > prev_num or num == prev_num:
                last_op[table] = ("CREATE", num)

    return frozenset(t for t, (op, _) in last_op.items() if op == "DROP")


def _diff_text(base_ref: str) -> str:
    try:
        r = subprocess.run(
            ["git", "diff", f"{base_ref}...HEAD", "--", "tests/"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=15,
        )
        if r.returncode == 0:
            return r.stdout
        r = subprocess.run(
            ["git", "diff", "HEAD", "--", "tests/"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=15,
        )
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def main() -> int:
    if os.environ.get("GITHUB_ACTIONS"):
        return 0

    base_ref = os.environ.get("DREAM_STUDIO_BASE_REF", "origin/main")
    diff = _diff_text(base_ref)
    if not diff:
        return 0

    dead = build_dead_table_ledger()
    violations: list[tuple[str, str]] = []

    for m in _DIFF_CREATE_RE.finditer(diff):
        table = m.group(1).lower()
        if _is_rename_intermediate(table):
            continue
        if table in dead:
            line = m.group(0).lstrip("+").strip()
            violations.append((table, line))

    if not violations:
        return 0

    print()
    print("=" * 70)
    print("DEAD-TABLE RESURRECTION: test diff adds CREATE TABLE for a dropped table")
    print("=" * 70)
    for table, line in violations:
        print(f"  Table: {table}")
        print(f"  Line:  {line[:110]}")
        print()
    print("These tables were permanently dropped by a numbered migration.")
    print("No production code creates them; the fixture would simulate a DB")
    print("state that can never exist in reality.")
    print()
    print("Correct fix: DELETE the test (dead subject) or fix the root cause")
    print("in the migration. Do not feed dead-table fixtures to keep tests alive.")
    print()
    print("Operator rule: tests are always removable.")
    print("=" * 70)
    print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
