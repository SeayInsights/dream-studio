#!/usr/bin/env python3
"""Dispatcher: UserPromptSubmit — single process for all prompt-fired hooks.

Replaces 6 subprocess invocations with one process that imports and calls
each handler sequentially. Reads stdin once and re-injects it before each
handler's main() so existing code works unchanged.

Handlers (in order):
  1. on-session-start    (runtime/hooks/meta)
  2. on-first-run        (runtime/hooks/meta)
  3. on-memory-retrieve  (runtime/hooks/meta)
  4. on-milestone-start  (runtime/hooks/core)
  5. on-context-threshold (runtime/hooks/meta)
  6. on-pulse            (runtime/hooks/meta)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _get_plugin_root() -> Path:
    sidecar = Path(__file__).resolve()
    for _ in range(6):
        candidate = sidecar / ".plugin-root"
        if candidate.is_file():
            try:
                return Path(candidate.read_text(encoding="utf-8").strip()).resolve()
            except Exception:
                pass
        sidecar = sidecar.parent
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[3]


PLUGIN_ROOT = _get_plugin_root()
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))
sys.path.insert(0, str(PLUGIN_ROOT / "hooks"))

from control.execution.dispatch_tracking import execute_handlers  # noqa: E402

HANDLERS: list[tuple[str, Path]] = [
    ("on-prompt-validate", PLUGIN_ROOT / "runtime" / "hooks" / "meta" / "on-prompt-validate.py"),
    ("on-session-start", PLUGIN_ROOT / "runtime" / "hooks" / "meta" / "on-session-start.py"),
    ("on-first-run", PLUGIN_ROOT / "runtime" / "hooks" / "meta" / "on-first-run.py"),
    ("on-memory-retrieve", PLUGIN_ROOT / "runtime" / "hooks" / "meta" / "on-memory-retrieve.py"),
    # Chain 7 — SQLite memory_entries injection (18.4.4).
    # Runs after file-based on-memory-retrieve; both write independent <xml> blocks.
    ("on-context-inject", PLUGIN_ROOT / "runtime" / "hooks" / "meta" / "on-context-inject.py"),
    ("on-milestone-start", PLUGIN_ROOT / "runtime" / "hooks" / "core" / "on-milestone-start.py"),
    (
        "on-context-threshold",
        PLUGIN_ROOT / "runtime" / "hooks" / "meta" / "on-context-threshold.py",
    ),
    ("on-pulse", PLUGIN_ROOT / "runtime" / "hooks" / "meta" / "on-pulse.py"),
]

STATE_DIR = Path.home() / ".dream-studio" / "state"


def main() -> None:
    raw_payload = sys.stdin.read()
    execute_handlers(HANDLERS, raw_payload, STATE_DIR)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
