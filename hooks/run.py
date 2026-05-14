#!/usr/bin/env python3
"""Cross-platform Dream Studio hook launcher.

This launcher is intentionally small: it resolves the plugin root, finds the
requested runtime hook, then replaces itself with that handler using the same
Python interpreter. Shell launchers remain available for direct use, but hook
registration should not depend on shell-specific environment expansion.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PACKS = ("core", "quality", "career", "analyze", "domains", "meta")


def resolve_plugin_root() -> Path:
    """Resolve the Dream Studio plugin root without requiring CLAUDE_PLUGIN_ROOT."""
    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_root:
        return Path(env_root).resolve()
    return Path(__file__).resolve().parents[1]


def resolve_handler(plugin_root: Path, handler: str) -> Path | None:
    """Find a handler in canonical runtime packs, then legacy migration path."""
    for pack in PACKS:
        candidate = plugin_root / "runtime" / "hooks" / pack / f"{handler}.py"
        if candidate.is_file():
            return candidate
    legacy = plugin_root / "hooks" / "handlers" / f"{handler}.py"
    if legacy.is_file():
        return legacy
    return None


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: run.py <handler-name> [args...]", file=sys.stderr)
        return 2

    handler = args[0]
    handler_args = args[1:]
    plugin_root = resolve_plugin_root()
    handler_path = resolve_handler(plugin_root, handler)
    if handler_path is None:
        print(f"run.py: handler not found: {handler}", file=sys.stderr)
        return 3

    os.environ["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)
    existing_pythonpath = os.environ.get("PYTHONPATH")
    pythonpath_parts = [str(plugin_root), str(plugin_root / "hooks")]
    if existing_pythonpath:
        pythonpath_parts.append(existing_pythonpath)
    os.environ["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)

    return subprocess.call([sys.executable, str(handler_path), *handler_args])


if __name__ == "__main__":
    raise SystemExit(main())
