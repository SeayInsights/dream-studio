#!/usr/bin/env python3
"""Hook: on-tool-activity — rolling snapshot of recent tool usage.

Trigger: PostToolUse.
Maintains activity feed at ~/.dream-studio/state/activity.json with recent tool calls.
"""

from __future__ import annotations

import json
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

from core.telemetry import tool_tracking  # noqa: E402


def main() -> None:
    try:
        raw = sys.stdin.read().lstrip("﻿")
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return

    tool_name = payload.get("tool_name", "unknown")
    tool_input = payload.get("tool_input", {})
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except Exception:
            tool_input = {}

    _PROTECTED_PATHS = ["settings.json", "settings.local.json", "CLAUDE.md"]
    _file_path = (tool_input.get("file_path") or tool_input.get("path") or "").replace("\\", "/")
    if any(p in _file_path for p in _PROTECTED_PATHS):
        return

    tool_tracking.maybe_harden_nudge(tool_name, tool_input)
    tool_tracking.maybe_security_suggest(tool_name, tool_input)
    tool_tracking.update_activity_feed(tool_name, tool_input)


if __name__ == "__main__":
    main()
