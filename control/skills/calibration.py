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

# Add project root to path for canonical imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import event emission bridge for dual-write pattern
try:
    from core.config import paths
    from core.event_store.legacy_bridge import LegacyBridge
    from core.event_store.event_store import EventStore
    from core.validation.event_validator import EventValidator

    _BRIDGE_AVAILABLE = True
except ImportError:
    _BRIDGE_AVAILABLE = False

_bridge_instance = None


def _get_bridge():
    """Lazy init of LegacyBridge for event emission."""
    global _bridge_instance
    if not _BRIDGE_AVAILABLE:
        return None
    if _bridge_instance is None:
        try:
            repo_root = Path(__file__).resolve().parents[2]
            docs_dir = repo_root / "docs" / "canonical"
            if not docs_dir.exists():
                return None

            taxonomy_path = str(docs_dir / "event_taxonomy_v1.json")
            schema_path = str(docs_dir / "canonical_event_v1_schema.json")

            if not Path(taxonomy_path).exists() or not Path(schema_path).exists():
                return None

            validator = EventValidator(taxonomy_path, schema_path)
            event_store = EventStore(
                db_path=str(paths.state_dir() / "studio.db"),
                validator=validator,
                emit_validation_failures=True,
            )
            _bridge_instance = LegacyBridge(event_store)
        except Exception:
            return None
    return _bridge_instance


def record_outcome(
    skill_name: str,
    model_used: str,
    outcome: str,
    duration: float,
    tokens: int,
) -> None:
    """Log skill execution outcome for model selection analysis.

    Args:
        skill_name: Full skill name (e.g., "ds-core")
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
        print(
            "Usage: skill_calibration.py check-mode <pack> <mode> <user-message>", file=sys.stderr
        )
        return 1

    pack = sys.argv[2]
    mode = sys.argv[3]
    user_message = sys.argv[4]

    # Import skill_router (relative import from same directory)
    try:
        from . import router as skill_router
    except ImportError:
        # Running as script, not as module
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from control.skills import router as skill_router  # type: ignore

    is_available, message = skill_router.is_mode_available(pack, mode, user_message)

    if not is_available:
        # Mode is locked - emit validation failed event
        try:
            bridge = _get_bridge()
            if bridge:
                mode_id = f"{pack}:{mode}"
                bridge.emit_from_legacy(
                    activity_type="event.validation.failed",
                    stream_id=f"skill-{mode_id}",
                    stream_type="skill",
                    event_data={
                        "pack": pack,
                        "mode": mode,
                        "locked_reason": "progressive_disclosure_check_failed",
                    },
                )
        except Exception:
            pass  # Never fail on event emission

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
    print(f"Unknown command: {command}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
