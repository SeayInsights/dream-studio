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

from lib.model_selector import get_model_for_skill  # noqa: E402
from lib.studio_db import insert_token_usage  # noqa: E402


def _build_display_name(skill_name: str, skill_args: str) -> tuple[str, str | None]:
    """Return ``(display_name, mode)`` from a raw skill name and args string.

    Strips the ``dream-studio:`` prefix from *skill_name* to obtain the pack
    component, then takes the first whitespace-delimited word of *skill_args*
    as the mode.  Examples::

        ("dream-studio:core", "think") -> ("core:think", "think")
        ("dream-studio:core", "")      -> ("core",       None)
        ("core",              "think") -> ("core:think", "think")
        ("unknown",           "")      -> ("unknown",    None)
    """
    pack = skill_name.removeprefix("dream-studio:")
    mode: str | None = skill_args.split()[0] if skill_args.strip() else None
    display_name = f"{pack}:{mode}" if mode else pack
    return display_name, mode


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
    skill_args = tool_input.get("args", "")
    skill_specifier = f"{skill_name} {skill_args}".strip() if skill_args else skill_name

    display_name, mode = _build_display_name(skill_name, skill_args)

    try:
        recommended_model = get_model_for_skill(skill_specifier)
    except Exception:
        recommended_model = "sonnet"

    state_dir = Path.home() / ".dream-studio" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "skill": display_name,
        "mode": mode or "",
        "session": payload.get("session_id", ""),
        "recommended_model": recommended_model,
    }

    log_path = state_dir / "skill-usage.jsonl"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    try:
        insert_token_usage(
            session_id=payload.get("session_id", ""),
            project_id=Path.cwd().name,
            skill_name=display_name,
            input_tokens=0,
            output_tokens=0,
            model=recommended_model,
        )
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
