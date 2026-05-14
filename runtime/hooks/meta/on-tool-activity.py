#!/usr/bin/env python3
"""Hook: on-tool-activity — rolling snapshot of recent tool usage.

Trigger: PostToolUse.
Maintains activity feed at ~/.dream-studio/state/activity.json with recent tool calls.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from core.telemetry import tool_tracking  # noqa: E402


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return

    tool_name = payload.get("tool_name", "unknown")
    tool_input = payload.get("tool_input", {})
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except Exception:
            tool_input = {}

    tool_tracking.maybe_harden_nudge(tool_name, tool_input)
    tool_tracking.maybe_security_suggest(tool_name, tool_input)
    tool_tracking.update_activity_feed(tool_name, tool_input)


if __name__ == "__main__":
    main()
