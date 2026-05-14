#!/usr/bin/env python3
"""Hook: on-skill-metrics — append skill usage record."""

import json, sys
from pathlib import Path
from control.execution.models.selector import get_model_for_skill
from core.event_store.studio_db import insert_token_usage
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
    try:
        insert_token_usage(
            session_id=payload.get("session_id", ""),
            project_id=Path.cwd().name,
            skill_name=display_name,
            input_tokens=0,
            output_tokens=0,
            model=model,
        )
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
