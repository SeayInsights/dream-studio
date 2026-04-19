#!/usr/bin/env python3
"""Hook: on-changelog-nudge — remind to update CHANGELOG.md when source files changed.

Trigger: Stop.
Checks git status: if tracked source files are modified/added but CHANGELOG.md is
not among them, prints a one-line advisory. Never blocks.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import paths  # noqa: E402

_SOURCE_EXTS = {".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs", ".sh", ".gd", ".cs"}
_SKIP_DIRS = {"tests", "test", "docs", "templates", "scripts", ".github", "__pycache__", "node_modules"}


def _git(args: list[str], cwd: Path) -> str:
    try:
        r = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def _find_project_root(start: Path) -> Path:
    """Walk up to the nearest .git or pyproject.toml."""
    p = start.resolve()
    for _ in range(8):
        if (p / ".git").exists() or (p / "pyproject.toml").exists():
            return p
        if p.parent == p:
            break
        p = p.parent
    return start


def main() -> None:
    try:
        json.loads(sys.stdin.read())
    except Exception:
        pass

    root = _find_project_root(paths.project_root())
    status = _git(["status", "--porcelain"], root)
    if not status:
        return

    source_changed = False
    changelog_changed = False

    for line in status.splitlines():
        if len(line) < 4:
            continue
        fname = line[3:].strip()
        p = Path(fname)

        if p.name.upper() in ("CHANGELOG.MD", "CHANGELOG"):
            changelog_changed = True
            continue

        if set(p.parts) & _SKIP_DIRS:
            continue

        if p.suffix.lower() in _SOURCE_EXTS:
            source_changed = True

    if source_changed and not changelog_changed:
        print(
            "\n[dream-studio] Source files changed — CHANGELOG.md not updated. Consider adding an entry.\n",
            flush=True,
        )


if __name__ == "__main__":
    main()
