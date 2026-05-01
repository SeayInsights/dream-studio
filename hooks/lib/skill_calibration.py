#!/usr/bin/env python3
"""Skill calibration logging for model selection analysis.

Logs skill execution outcomes to .dream-studio/calibration.jsonl for
tracking which models work best for which skills over time.

Also provides CLI commands for:
- check-mode: Check if a skill mode is available in progressive disclosure mode
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def record_outcome(
    skill_name: str,
    model_used: str,
    outcome: str,
    duration: float,
    tokens: int,
) -> None:
    """Log skill execution outcome for model selection analysis.

    Args:
        skill_name: Full skill name (e.g., "dream-studio:core")
        model_used: Model identifier ("haiku", "sonnet", "opus")
        outcome: Execution result ("success" or "failure")
        duration: Execution time in seconds
        tokens: Total token count (input + output)
    """
    calibration_dir = Path.home() / ".dream-studio"
    calibration_dir.mkdir(parents=True, exist_ok=True)
    calibration_path = calibration_dir / "calibration.jsonl"

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "skill": skill_name,
        "model": model_used,
        "outcome": outcome,
        "duration_s": round(duration, 2),
        "tokens": tokens,
    }

    with calibration_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def cli_check_mode() -> int:
    """CLI command: check-mode <pack> <mode> <user-message>

    Checks if a mode is available in progressive disclosure mode.
    Prints unlock message if locked, unlock notifications if just unlocked.

    Returns:
        0 if mode is available (continue execution)
        1 if mode is locked (stop execution)
    """
    # Args: [script, "check-mode", pack, mode, user-message]
    if len(sys.argv) < 5:
        print("Usage: skill_calibration.py check-mode <pack> <mode> <user-message>", file=sys.stderr)
        return 1

    pack = sys.argv[2]
    mode = sys.argv[3]
    user_message = sys.argv[4]

    # Import skill_router (relative import from same lib directory)
    try:
        from . import skill_router
    except ImportError:
        # Running as script, not as module
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from lib import skill_router  # type: ignore

    is_available, message = skill_router.is_mode_available(pack, mode, user_message)

    if not is_available:
        # Mode is locked
        print(message, flush=True)
        return 1

    # Mode is available
    if message:
        # Mode was just unlocked - show notification
        skill_router.show_unlock_notification(message)

    return 0


def main() -> int:
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: skill_calibration.py <command> [args...]", file=sys.stderr)
        return 1

    command = sys.argv[1]

    if command == "check-mode":
        return cli_check_mode()
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
