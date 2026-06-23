#!/usr/bin/env python3
"""Skill router — progressive disclosure gate for dream-studio skills.

Checks if the user is in progressive mode and whether the requested skill/mode
is unlocked. If locked, shows an unlock prompt and checks if the user's message
contains unlock trigger patterns.

Called by skill invocation hooks before loading a skill.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

# Add project root to path for canonical imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.config import paths
from core.config import state

# Decision transparency layer
from core.decisions import emit_decision

# Import event emission bridge for dual-write pattern
try:
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


def _load_progressive_config() -> dict[str, Any]:
    """Load progressive-disclosure.yml from setup skill."""
    try:
        config_path = (
            paths.plugin_root()
            / "canonical"
            / "skills"
            / "setup"
            / "modes"
            / "wizard"
            / "progressive-disclosure.yml"
        )
        if not config_path.is_file():
            return {"starter_modes": [], "total_modes": 40, "starter_count": 5}

        if yaml is None:
            return {"starter_modes": [], "total_modes": 40, "starter_count": 5}

        with config_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {"starter_modes": [], "total_modes": 40, "starter_count": 5}


def _load_unlock_conditions() -> dict[str, Any]:
    """Load unlock-conditions.yml from setup skill."""
    try:
        config_path = (
            paths.plugin_root()
            / "canonical"
            / "skills"
            / "setup"
            / "modes"
            / "wizard"
            / "unlock-conditions.yml"
        )
        if not config_path.is_file():
            return {"unlock_triggers": []}

        if yaml is None:
            return {"unlock_triggers": []}

        with config_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {"unlock_triggers": []}


def _get_unlocked_modes() -> set[str]:
    """Get set of unlocked mode identifiers from config.

    Returns set of strings like "core:think", "security:scan", etc.
    """
    try:
        cfg = state.read_config()
        unlocked = cfg.get("unlocked_modes", [])
        if not isinstance(unlocked, list):
            return set()
        return set(unlocked)
    except Exception:
        return set()


def _save_unlocked_modes(unlocked: set[str]) -> None:
    """Save unlocked mode identifiers to config."""
    try:
        cfg = state.read_config()
        cfg["unlocked_modes"] = sorted(list(unlocked))
        state.write_config(cfg)
    except Exception:
        pass


def _get_starter_modes() -> set[str]:
    """Get set of starter mode identifiers (pack:mode format)."""
    config = _load_progressive_config()
    starter = config.get("starter_modes", [])

    modes = set()
    for mode_def in starter:
        if isinstance(mode_def, dict):
            pack = mode_def.get("pack")
            mode = mode_def.get("mode")
            if pack and mode:
                modes.add(f"{pack}:{mode}")

    return modes


def _check_unlock_patterns(user_message: str) -> list[dict[str, Any]]:
    """Check if user's message contains any unlock trigger patterns.

    Returns list of unlock configs that matched, enriched with match reasoning.

    DECISION TRANSPARENCY:
    Each match includes explicit reasoning about WHY it matched, enabling
    post-hoc analysis of unlock decisions.
    """
    if not user_message:
        return []

    conditions = _load_unlock_conditions()
    triggers = conditions.get("unlock_triggers", [])

    matched = []
    message_lower = user_message.lower()

    for trigger in triggers:
        if not isinstance(trigger, dict):
            continue

        patterns = trigger.get("patterns", [])
        if not patterns:
            continue

        # Check if any pattern matches
        for pattern in patterns:
            if not isinstance(pattern, str):
                continue

            # Simple case-insensitive substring match
            if pattern.lower() in message_lower:
                # Enrich trigger with match reasoning
                match_confidence = 0.4  # Heuristic: substring match is low-confidence signal
                trigger_with_reasoning = trigger.copy()
                trigger_with_reasoning["_match_info"] = {
                    "matched_pattern": pattern,
                    "match_type": "substring",
                    "reason": f"Pattern '{pattern}' found in user message",
                    "confidence": match_confidence,
                }

                # Emit decision for pattern match
                emit_decision(
                    decision_type="unlock_pattern.match",
                    context={
                        "user_message": user_message[:200],  # Truncate for privacy
                        "pattern": pattern,
                        "pack": trigger.get("pack", "unknown"),
                    },
                    outcome="matched",
                    reasoning={
                        "match_type": "substring",
                        "rationale": f"Pattern '{pattern}' found in user message",
                        "matched_pattern": pattern,
                    },
                    confidence=match_confidence,
                    policy_applied="UNLOCK_PATTERNS_V1",
                    source_subsystem="skill_router",
                )

                matched.append(trigger_with_reasoning)
                break  # Don't check other patterns for this trigger

    return matched


def _unlock_modes(trigger_configs: list[dict[str, Any]]) -> list[str]:
    """Unlock modes from trigger configs and return unlock messages.

    Returns list of unlock messages to show to user.

    DECISION TRANSPARENCY:
    Unlock decisions are logged with explicit reasoning from match_info
    when available, enabling audit trail of feature unlocks.
    """
    unlocked = _get_unlocked_modes()
    messages = []

    for trigger in trigger_configs:
        pack = trigger.get("pack")
        modes_to_unlock = trigger.get("modes_unlocked", [])
        unlock_msg = trigger.get("unlock_message", "")
        match_info = trigger.get("_match_info", {})  # Extract reasoning if present

        if not pack or not modes_to_unlock:
            continue

        # Build mode identifiers
        newly_unlocked = []
        for mode in modes_to_unlock:
            mode_id = f"{pack}:{mode}"
            if mode_id not in unlocked:
                unlocked.add(mode_id)
                newly_unlocked.append(mode_id)

        # Emit unlock event with reasoning (if bridge available)
        if newly_unlocked:
            bridge = _get_bridge()
            if bridge:
                try:
                    bridge.emit_from_legacy(
                        activity_type="skill.mode.unlocked",
                        stream_id=pack,
                        stream_type="skill_unlock",
                        event_data={
                            "pack": pack,
                            "modes_unlocked": newly_unlocked,
                            "unlock_reason": match_info.get("reason", "Manual unlock"),
                            "matched_pattern": match_info.get("matched_pattern", "unknown"),
                            "confidence": match_info.get("confidence", 0.0),
                        },
                        status="completed",
                        severity="info",
                    )
                except Exception:
                    pass  # Don't fail on event emission

        # Only show message if we actually unlocked something new
        if newly_unlocked and unlock_msg:
            messages.append(unlock_msg.strip())

    # Save updated unlock state
    _save_unlocked_modes(unlocked)

    return messages


def is_progressive_mode() -> bool:
    """Check if user is in progressive disclosure mode."""
    try:
        cfg = state.read_config()
        mode = cfg.get("onboarding_mode", "full")
        return mode == "progressive"
    except Exception:
        return False


def is_mode_available(pack: str, mode: str, user_message: str = "") -> tuple[bool, str]:
    """Check if a skill mode is available to the user.

    Args:
        pack: Pack name (e.g., "core", "security")
        mode: Mode name (e.g., "think", "scan")
        user_message: User's message (used to check for unlock triggers)

    Returns:
        (is_available, message) — message is empty if available, else unlock prompt
    """
    # If not in progressive mode, all modes are available
    if not is_progressive_mode():
        return (True, "")

    mode_id = f"{pack}:{mode}"

    # Check if mode is in starter set
    starter = _get_starter_modes()
    if mode_id in starter:
        return (True, "")

    # Check if mode is already unlocked
    unlocked = _get_unlocked_modes()
    if mode_id in unlocked:
        return (True, "")

    # Mode is locked — check if user's message contains unlock triggers
    if user_message:
        matched_triggers = _check_unlock_patterns(user_message)
        if matched_triggers:
            messages = _unlock_modes(matched_triggers)

            # Check if the requested mode is now unlocked
            unlocked = _get_unlocked_modes()
            if mode_id in unlocked:
                # Mode was just unlocked!
                unlock_msg = "\n\n".join(messages)
                return (True, unlock_msg)

    # Mode is still locked
    config = _load_progressive_config()
    welcome = config.get("welcome_message", "")

    unlock_msg = (
        f"\n[dream-studio] Mode '{pack}:{mode}' is not yet unlocked.\n\n"
        f"You're in progressive disclosure mode. Use related keywords to unlock packs.\n"
        f"For example, mention 'security' or 'scan' to unlock the security pack.\n\n"
        f"Run `ds-setup status` to see what's available.\n"
        f"To switch to full mode (all 40 modes), run: /config set onboarding_mode full\n"
    )

    return (False, unlock_msg)


def show_unlock_notification(message: str) -> None:
    """Print an unlock notification message."""
    if message:
        print(f"\n{message}\n", flush=True)


def get_progressive_status() -> dict[str, Any]:
    """Get current progressive mode status for display.

    Returns dict with:
        - mode: "progressive" or "full"
        - starter_count: number of starter modes
        - unlocked_count: number of unlocked modes
        - total_count: total number of modes
        - starter_modes: list of starter mode IDs
        - unlocked_modes: list of unlocked mode IDs
    """
    mode = "full"
    try:
        cfg = state.read_config()
        mode = cfg.get("onboarding_mode", "full")
    except Exception:
        pass

    config = _load_progressive_config()
    starter = _get_starter_modes()
    unlocked = _get_unlocked_modes()

    total = config.get("total_modes", 40)

    if mode != "progressive":
        # In full mode, everything is available
        return {
            "mode": "full",
            "starter_count": 0,
            "unlocked_count": total,
            "total_count": total,
            "starter_modes": [],
            "unlocked_modes": [],
        }

    # In progressive mode
    all_available = starter | unlocked

    return {
        "mode": "progressive",
        "starter_count": len(starter),
        "unlocked_count": len(unlocked),
        "total_count": total,
        "available_count": len(all_available),
        "starter_modes": sorted(list(starter)),
        "unlocked_modes": sorted(list(unlocked)),
    }


def gate_skill_invocation(payload: dict) -> None:
    """Gate skill invocations for progressive disclosure.

    Checks if the requested skill mode is available and shows unlock
    messages if locked. Handles unlock triggers in user messages.

    Args:
        payload: PostToolUse payload dict containing tool_name, tool_input, user_message
    """
    tool_name = payload.get("tool_name", "")
    if tool_name != "Skill":
        return

    tool_input = payload.get("tool_input", {})
    if isinstance(tool_input, str):
        try:
            import json

            tool_input = json.loads(tool_input)
        except Exception:
            tool_input = {}

    skill_full = tool_input.get("skill", "")
    if not skill_full:
        return

    # Parse pack name
    if ":" in skill_full:
        parts = skill_full.split(":", 1)
        if parts[0] == "dream-studio" and len(parts) > 1:
            pack = parts[1]
        else:
            return  # Not a dream-studio skill
    else:
        pack = skill_full

    # Mode is in args (first word)
    args = tool_input.get("args", "")
    mode = args.split()[0] if args else ""

    if not mode:
        return  # Can't gate without mode

    # Check mode availability
    user_message = payload.get("user_message", "")
    is_available, message = is_mode_available(pack, mode, user_message)

    # Emit events for routing decisions
    try:
        bridge = _get_bridge()
        if bridge:
            skill_id = f"{pack}:{mode}"
            if is_available:
                bridge.emit_from_legacy(
                    activity_type="skill.execution.started",
                    stream_id=f"skill-{skill_id}",
                    stream_type="skill",
                    event_data={
                        "skill_name": skill_id,
                        "pack": pack,
                        "mode": mode,
                        "is_locked": False,
                    },
                )
            else:
                bridge.emit_from_legacy(
                    activity_type="event.validation.failed",
                    stream_id=f"skill-{skill_id}",
                    stream_type="skill",
                    event_data={
                        "skill_name": skill_id,
                        "pack": pack,
                        "mode": mode,
                        "is_locked": True,
                        "reason": "progressive_disclosure",
                    },
                )
    except Exception:
        pass  # Never fail on event emission

    if not is_available:
        print(message, flush=True)
    elif message:
        show_unlock_notification(message)
