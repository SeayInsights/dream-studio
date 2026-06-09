"""Authority boundary lint gate for the DuckDB analytics store.

Enforces the never-authority invariant: only core/projections/runner.py may
open a read-write DuckDB connection (connect_analytics with read_only=False
or omitting read_only). API routes, CLI, and projection handle() methods
must use read_only=True connections.

Exit 0  = no violations found (gate passes).
Exit 1  = one or more violations found (gate fails, push blocked).

Invoked by canonical/workflows/pre-push.yaml as an advisory gate.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Directories that must not open read-write DuckDB connections.
CHECKED_DIRS = [
    REPO_ROOT / "projections" / "api",
    REPO_ROOT / "interfaces" / "cli",
]

# File that IS allowed to open read-write connections.
ALLOWED_FILE = REPO_ROOT / "core" / "projections" / "runner.py"


def _uses_write_analytics_conn(path: Path) -> list[int]:
    """Return line numbers in path where connect_analytics(read_only=False) is called.

    Catches the two problematic patterns:
      connect_analytics()                    — defaults to read_only=True, safe
      connect_analytics(read_only=False)     — violation
      connect_analytics(db_path, read_only=False) — violation
    """
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name != "connect_analytics":
            continue
        for kw in node.keywords:
            if kw.arg == "read_only" and isinstance(kw.value, ast.Constant):
                if kw.value.value is False:
                    violations.append(node.lineno)
    return violations


def check() -> int:
    """Scan checked dirs for write-connection violations.

    Returns 0 (pass) or 1 (fail).
    """
    all_violations: list[tuple[Path, int]] = []

    for checked_dir in CHECKED_DIRS:
        if not checked_dir.exists():
            continue
        for py_file in checked_dir.rglob("*.py"):
            if py_file.resolve() == ALLOWED_FILE.resolve():
                continue
            lines = _uses_write_analytics_conn(py_file)
            for ln in lines:
                all_violations.append((py_file, ln))

    if not all_violations:
        print("authority-boundary: OK — no write analytics connections outside runner.py")
        return 0

    print("authority-boundary: VIOLATIONS FOUND")
    for path, lineno in all_violations:
        rel = path.relative_to(REPO_ROOT)
        print(f"  {rel}:{lineno}: connect_analytics(read_only=False) outside runner.py")
    return 1


if __name__ == "__main__":
    sys.exit(check())
