#!/usr/bin/env python3
"""Hook: on-skill-load — log skill reads and resolve director_name.

Trigger: PostToolUse on Read.
Purpose: Append skill reads to `~/.dream-studio/meta/skill-usage.log`
and — when the file content contains the `{{director_name}}` placeholder
and a director_name is set in config.json — emit a reminder with the
resolved value so downstream agents can address the user correctly.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import paths, state  # noqa: E402

SKILL_PATTERN = re.compile(r"skills[\\/].+\.md$")
DIRECTOR_PLACEHOLDER = "{{director_name}}"


def extract_skill_name(file_path: str) -> str:
    normalized = file_path.replace("\\", "/")
    match = re.search(r"skills/(.+)\.md$", normalized)
    return match.group(1) if match else Path(file_path).stem


def _is_safe_skill_path(file_path: str) -> bool:
    """Reject symlinks that resolve outside the user's home directory."""
    try:
        p = Path(file_path)
        if not p.is_symlink():
            return True
        resolved = p.resolve()
        home = Path.home().resolve()
        return str(resolved).replace("\\", "/").startswith(str(home).replace("\\", "/"))
    except Exception:
        return False


def maybe_announce_director(file_path: str) -> None:
    """If the read file contains the placeholder, surface the resolved value."""
    if not _is_safe_skill_path(file_path):
        return
    try:
        content = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return
    if DIRECTOR_PLACEHOLDER not in content:
        return
    try:
        director = state.read_config().get("director_name")
    except Exception:
        director = None
    if not director:
        return
    print(
        f"\n[dream-studio] {DIRECTOR_PLACEHOLDER} in the file you read resolves to '{director}'.\n",
        flush=True,
    )


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except Exception:
            tool_input = {}

    if tool_name != "Read":
        return

    file_path = tool_input.get("file_path", "")
    if not file_path or not SKILL_PATTERN.search(file_path.replace("\\", "/")):
        return

    skill_name = extract_skill_name(file_path)
    timestamp = datetime.now(timezone.utc).isoformat()
    session_id = os.environ.get("CLAUDE_SESSION_ID", "unknown")

    print(f"\n[dream-studio] Skill loaded: {skill_name}\n", flush=True)

    try:
        log_path = paths.meta_dir() / "skill-usage.log"
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"{timestamp}\t{skill_name}\t{session_id}\n")
    except Exception:
        pass

    maybe_announce_director(file_path)


if __name__ == "__main__":
    main()
