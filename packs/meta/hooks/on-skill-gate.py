#!/usr/bin/env python3
"""Hook: on-skill-gate — Progressive disclosure gate for skill invocations.

Trigger: PreToolUse on Skill tool.

If the user is in progressive mode and the requested skill mode is locked,
print a message that Claude sees explaining the mode is locked and showing
how to unlock it.

If the user's message contains unlock trigger patterns, unlock matching packs
and show unlock notifications.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hooks"))

from lib import skill_router  # noqa: E402


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return

    tool_name = payload.get("tool_name", "")
    if tool_name != "Skill":
        return

    tool_input = payload.get("tool_input", {})
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except Exception:
            tool_input = {}

    # Extract skill name and args
    skill_full = tool_input.get("skill", "")
    if not skill_full:
        return

    # Parse pack and mode from skill name (format: "dream-studio:pack" or "pack")
    # Args may contain the mode
    args = tool_input.get("args", "")

    # Parse pack name
    if ":" in skill_full:
        parts = skill_full.split(":", 1)
        if parts[0] == "dream-studio" and len(parts) > 1:
            pack = parts[1]
        else:
            # Not a dream-studio skill, allow it
            return
    else:
        # Simple skill name like "core", "security", etc.
        pack = skill_full

    # Mode is in args (first word)
    mode = args.split()[0] if args else ""

    # If no mode specified, we can't gate it yet (the skill will handle mode inference)
    # So we'll let it through and check on the next invocation
    if not mode:
        return

    # Get user's message to check for unlock triggers
    user_message = payload.get("user_message", "")

    # Check if mode is available
    is_available, message = skill_router.is_mode_available(pack, mode, user_message)

    if not is_available:
        # Mode is locked - show the unlock message
        print(message, flush=True)
        return

    # Mode is available
    if message:
        # Mode was just unlocked! Show the unlock notification
        skill_router.show_unlock_notification(message)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # Never block skill invocation on gate failure
