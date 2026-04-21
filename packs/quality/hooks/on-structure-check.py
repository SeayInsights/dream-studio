#!/usr/bin/env python3
"""Hook: on-structure-check — nudge when source files are placed outside standard dirs.

Trigger: PostToolUse (Write only — creating new files).
Checks FSC conventions: .py/.ts/.js source files should live in src/, lib/, hooks/,
app/, or tests/ — not scattered at the project root. Advisory only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hooks"))

from lib import paths  # noqa: E402

_SOURCE_EXTS = {".py", ".ts", ".js", ".tsx", ".jsx"}

# Files allowed at root level
_ROOT_ALLOWLIST = {
    "setup.py", "conftest.py", "manage.py", "wsgi.py", "asgi.py",
    "app.py", "main.py", "index.js", "index.ts", "next.config.js",
    "next.config.ts", "vite.config.ts", "vite.config.js",
    "tailwind.config.js", "tailwind.config.ts",
}

# Top-level dirs that are non-standard names for source code
_NONSTANDARD_DIRS = {"util", "utils", "helper", "helpers", "common", "shared", "misc"}


def _find_project_root(file_path: str) -> Path:
    p = Path(file_path).resolve().parent
    for _ in range(10):
        if (p / ".git").exists() or (p / "pyproject.toml").exists():
            return p
        if p.parent == p:
            break
        p = p.parent
    return Path(file_path).resolve().parent


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return

    if payload.get("tool_name") != "Write":
        return

    tool_input = payload.get("tool_input", {})
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except Exception:
            return

    fp = tool_input.get("file_path", "")
    if not fp:
        return

    p = Path(fp)
    if p.suffix.lower() not in _SOURCE_EXTS:
        return

    root = _find_project_root(fp)
    try:
        rel = p.resolve().relative_to(root)
    except ValueError:
        return

    parts = rel.parts
    if len(parts) == 0:
        return

    msg = None
    if len(parts) == 1:
        # File directly at project root
        if p.name not in _ROOT_ALLOWLIST:
            msg = f"{p.name} is at the project root — consider placing source files in src/ or lib/."
    elif len(parts) >= 2:
        top = parts[0].lower()
        if top in _NONSTANDARD_DIRS:
            msg = f"{parts[0]}/ is a non-standard directory name — consider src/ or lib/ instead."

    if msg:
        slug = str(root).replace("\\", "-").replace("/", "-").replace(":", "-")[:80]
        key = f"structure-{slug}-{p.name}"
        sentinel = paths.state_dir() / f"{key}.json"
        if sentinel.exists():
            return
        try:
            sentinel.parent.mkdir(parents=True, exist_ok=True)
            sentinel.write_text("{}", encoding="utf-8")
        except Exception:
            return
        print(f"\n[dream-studio] Structure: {msg} Run /structure-audit for a full report.\n", flush=True)


if __name__ == "__main__":
    main()
