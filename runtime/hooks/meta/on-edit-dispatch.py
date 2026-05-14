#!/usr/bin/env python3
"""Dispatcher: PostToolUse Edit|Write — single process for all edit/write hooks.

Replaces 4 subprocess invocations with one process that imports and calls
each handler sequentially. Reads stdin once and re-injects it before each
handler's main() so existing code works unchanged.

Handlers (in order):
  1. on-agent-correction (runtime/hooks/quality)
  2. on-game-validate    (runtime/hooks/domains)
  3. on-security-scan    (runtime/hooks/quality)
  4. on-structure-check  (runtime/hooks/quality)
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PLUGIN_ROOT / "hooks"))

from control.execution.dispatch_tracking import run_handlers  # noqa: E402

HANDLERS = [
    (
        "on-agent-correction",
        PLUGIN_ROOT / "runtime" / "hooks" / "quality" / "on-agent-correction.py",
    ),
    ("on-game-validate", PLUGIN_ROOT / "runtime" / "hooks" / "domains" / "on-game-validate.py"),
    ("on-security-scan", PLUGIN_ROOT / "runtime" / "hooks" / "quality" / "on-security-scan.py"),
    ("on-structure-check", PLUGIN_ROOT / "runtime" / "hooks" / "quality" / "on-structure-check.py"),
]

STATE_DIR = Path.home() / ".dream-studio" / "state"


def main() -> None:
    raw_payload = sys.stdin.read()
    run_handlers(HANDLERS, raw_payload, "PostToolUse_Edit_Write", STATE_DIR)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
