#!/usr/bin/env python3
"""Hook: on-milestone-start — write a marker when a DCL command opens a milestone.

Trigger: UserPromptSubmit matching a build/deploy DCL command.
Purpose: Persist a milestone marker to `~/.dream-studio/state/milestone-active.txt`
so `on-milestone-end` (and advisory hooks) can detect an in-flight milestone.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _get_plugin_root() -> Path:
    sidecar = Path(__file__).resolve()
    for _ in range(8):
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
    return Path(__file__).resolve().parents[4]


_PLUGIN_ROOT = _get_plugin_root()
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))
if str(_PLUGIN_ROOT / "hooks") not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT / "hooks"))

from core.utils import milestone
from core.config import paths  # noqa: E402


def main() -> None:
    message = milestone.read_user_message()
    if not message or not milestone.is_dcl_command(message):
        return

    if milestone.marker_exists(paths.state_dir()):
        milestone.print_already_active(message)
        return

    if milestone.create_marker(message, paths.state_dir()):
        milestone.print_workflow_reminder(message)
    else:
        print("[on-milestone-start] failed to write marker", flush=True)


if __name__ == "__main__":
    main()
