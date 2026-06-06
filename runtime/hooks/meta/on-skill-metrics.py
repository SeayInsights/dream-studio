#!/usr/bin/env python3
"""Hook: on-skill-metrics — append skill usage record."""

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

from control.execution.models.selector import get_model_for_skill
from control.skills.metrics import build_display_name, write_skill_usage


def main() -> None:
    try:
        payload = json.loads(raw) if (raw := sys.stdin.read()).strip() else {}
    except Exception:
        payload = {}
    tool_input = payload.get("tool_input", {})
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except Exception:
            tool_input = {}
    skill_name = tool_input.get("skill") or tool_input.get("name") or "unknown"
    skill_args = tool_input.get("args", "")
    display_name, mode = build_display_name(skill_name, skill_args)
    try:
        model = get_model_for_skill(
            f"{skill_name} {skill_args}".strip() if skill_args else skill_name
        )
    except Exception:
        model = "unspecified"
    write_skill_usage(
        Path.home() / ".dream-studio" / "state",
        display_name,
        mode,
        payload.get("session_id", ""),
        model,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
