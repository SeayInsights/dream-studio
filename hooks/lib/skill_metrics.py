"""
Append a usage record to ~/.dream-studio/state/skill-usage.jsonl
Called by the PostToolUse hook on Skill tool invocations.

Usage: py skill_metrics.py <skill_name> <model>
Exits 0 always — metrics failure must not block skill execution.
"""

import sys
import json
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    skill_name = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    model = sys.argv[2] if len(sys.argv) > 2 else "unknown"

    state_dir = Path.home() / ".dream-studio" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "skill": skill_name,
        "model": model,
        "session": "dream-studio",
    }

    log_path = state_dir / "skill-usage.jsonl"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # Never block skill execution on metrics failure
