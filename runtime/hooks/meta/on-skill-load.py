#!/usr/bin/env python3
"""Hook: on-skill-load — log skill reads and resolve director_name."""

import json, os, re, sys
from datetime import datetime, timezone
from pathlib import Path
from core.config import paths
from core.config import state as config_state
from control.skills.loader import extract_skill_name, resolve_director_placeholder


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return
    tool_input = payload.get("tool_input", {})
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except Exception:
            tool_input = {}
    if payload.get("tool_name") != "Read":
        return
    file_path = tool_input.get("file_path", "")
    skill_pat = re.compile(r"skills[\\/].+\.md$")
    examples_pat = re.compile(r"examples\.md$")
    if not file_path or not skill_pat.search(file_path.replace("\\", "/")):
        return
    if examples_pat.search(file_path.replace("\\", "/")):
        return

    skill_name = extract_skill_name(file_path)
    print(f"\n[dream-studio] Skill loaded: {skill_name}\n", flush=True)

    try:
        log_path = paths.meta_dir() / "skill-usage.log"
        with log_path.open("a", encoding="utf-8") as f:
            f.write(
                f"{datetime.now(timezone.utc).isoformat()}\t{skill_name}\t{os.environ.get('CLAUDE_SESSION_ID', 'unknown')}\n"
            )
    except Exception:
        pass

    try:
        director = config_state.read_config().get("director_name")
    except Exception:
        director = None
    if resolved := resolve_director_placeholder(file_path, director):
        print(f"\n[dream-studio] {{{{director_name}}}} resolves to '{resolved}'.\n", flush=True)


if __name__ == "__main__":
    main()
