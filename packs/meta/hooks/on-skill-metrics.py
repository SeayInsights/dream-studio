#!/usr/bin/env python3
"""Hook: on-skill-metrics — append a usage record on every Skill tool invocation.

Trigger: PostToolUse on Skill tool.

Reads the skill name from the PostToolUse payload (tool_input.skill).
Writes a JSONL record to ~/.dream-studio/state/skill-usage.jsonl.
Exits 0 always — metrics failure must never block skill execution.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hooks"))


def main() -> None:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    tool_input = payload.get("tool_input", {})
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except Exception:
            tool_input = {}

    skill_name = tool_input.get("skill") or tool_input.get("name") or "unknown"

    state_dir = Path.home() / ".dream-studio" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "skill": skill_name,
        "session": payload.get("session_id", ""),
    }

    log_path = state_dir / "skill-usage.jsonl"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
