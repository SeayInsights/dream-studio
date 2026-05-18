#!/usr/bin/env python3
"""Tool-agnostic hook event dispatcher.

Input contract:
  argv[1]: event name (UserPromptSubmit | Stop | PostToolUse | PostCompact)
  stdin:   JSON payload; PostToolUse payloads must include toolName field

Routes to handler scripts in runtime/hooks/{pack}/ based on event name and
toolName. Always exits 0.

Tool-specific emitters normalize their native payload into this contract
before calling this dispatcher. This module contains no tool-specific logic.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _get_plugin_root() -> Path:
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return Path(env).resolve()
    # Installed to ~/.claude/hooks/dispatch/ — sidecar is one level up in hooks/
    sidecar = Path(__file__).parent.parent / ".plugin-root"
    if sidecar.is_file():
        try:
            return Path(sidecar.read_text(encoding="utf-8").strip()).resolve()
        except Exception:
            pass
    return Path(__file__).resolve().parents[2]


def _h(plugin_root: Path, pack: str, name: str) -> tuple[str, Path]:
    return (name, plugin_root / "runtime" / "hooks" / pack / f"{name}.py")


def _resolve_handlers(
    event_name: str, tool_name: str, plugin_root: Path
) -> list[tuple[str, Path]]:
    """Return (name, path) list for the given event and tool_name."""
    if event_name == "UserPromptSubmit":
        return [_h(plugin_root, "meta", "on-prompt-dispatch")]
    if event_name == "Stop":
        return [_h(plugin_root, "meta", "on-stop-dispatch")]
    if event_name == "PostCompact":
        return [_h(plugin_root, "meta", "on-post-compact")]
    if event_name == "PostToolUse":
        handlers = [_h(plugin_root, "meta", "on-tool-activity")]
        if tool_name == "Skill":
            handlers += [
                _h(plugin_root, "meta", "on-skill-metrics"),
                _h(plugin_root, "meta", "on-skill-complete"),
            ]
        elif tool_name in ("Edit", "Write", "MultiEdit"):
            handlers += [_h(plugin_root, "meta", "on-edit-dispatch")]
        elif tool_name == "Read":
            handlers += [_h(plugin_root, "meta", "on-skill-load")]
        return handlers
    return []


def main() -> int:
    if len(sys.argv) < 2:
        return 0

    event_name = sys.argv[1]

    try:
        raw_payload = sys.stdin.read()
    except Exception:
        raw_payload = "{}"

    try:
        payload = json.loads(raw_payload) if raw_payload.strip() else {}
    except (json.JSONDecodeError, ValueError):
        payload = {}

    tool_name: str = payload.get("toolName", "")

    try:
        plugin_root = _get_plugin_root()
        if str(plugin_root) not in sys.path:
            sys.path.insert(0, str(plugin_root))

        import control.execution.dispatch_tracking as _dt  # noqa: PLC0415

        state_dir = Path.home() / ".dream-studio" / "state"
        handlers = _resolve_handlers(event_name, tool_name, plugin_root)
        if handlers:
            _dt.run_handlers(handlers, raw_payload, event_name, state_dir)
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
