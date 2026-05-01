#!/usr/bin/env python3
"""Skill router — progressive disclosure gate for dream-studio skills.

Checks if the user is in progressive mode and whether the requested skill/mode
is unlocked. If locked, shows an unlock prompt and checks if the user's message
contains unlock trigger patterns.

Called by skill invocation hooks before loading a skill.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Set

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

from . import paths, state


def _load_progressive_config() -> Dict[str, Any]:
    """Load progressive-disclosure.yml from setup skill."""
    try:
        config_path = (
            paths.plugin_root()
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


def _load_unlock_conditions() -> Dict[str, Any]:
    """Load unlock-conditions.yml from setup skill."""
    try:
        config_path = (
            paths.plugin_root()
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


def _get_unlocked_modes() -> Set[str]:
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


def _save_unlocked_modes(unlocked: Set[str]) -> None:
    """Save unlocked mode identifiers to config."""
    try:
        cfg = state.read_config()
        cfg["unlocked_modes"] = sorted(list(unlocked))
        state.write_config(cfg)
    except Exception:
        pass


def _get_starter_modes() -> Set[str]:
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


def _check_unlock_patterns(user_message: str) -> List[Dict[str, Any]]:
    """Check if user's message contains any unlock trigger patterns.

    Returns list of unlock configs that matched.
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
                matched.append(trigger)
                break  # Don't check other patterns for this trigger

    return matched


def _unlock_modes(trigger_configs: List[Dict[str, Any]]) -> List[str]:
    """Unlock modes from trigger configs and return unlock messages.

    Returns list of unlock messages to show to user.
    """
    unlocked = _get_unlocked_modes()
    messages = []

    for trigger in trigger_configs:
        pack = trigger.get("pack")
        modes_to_unlock = trigger.get("modes_unlocked", [])
        unlock_msg = trigger.get("unlock_message", "")

        if not pack or not modes_to_unlock:
            continue

        # Build mode identifiers
        newly_unlocked = []
        for mode in modes_to_unlock:
            mode_id = f"{pack}:{mode}"
            if mode_id not in unlocked:
                unlocked.add(mode_id)
                newly_unlocked.append(mode_id)

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
        f"Run `dream-studio:setup status` to see what's available.\n"
        f"To switch to full mode (all 40 modes), run: /config set onboarding_mode full\n"
    )

    return (False, unlock_msg)


def show_unlock_notification(message: str) -> None:
    """Print an unlock notification message."""
    if message:
        print(f"\n{message}\n", flush=True)


def get_progressive_status() -> Dict[str, Any]:
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
