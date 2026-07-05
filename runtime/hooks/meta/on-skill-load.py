#!/usr/bin/env python3
"""Hook: on-skill-load — log skill reads and resolve director_name."""

import json
import os
import re
import sys
from datetime import datetime, UTC
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

from core.config import paths
from core.config import state as config_state
from control.skills.loader import extract_skill_name, resolve_director_placeholder


def main() -> None:
    try:
        raw = sys.stdin.read().lstrip("﻿")
        payload = json.loads(raw) if raw.strip() else {}
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
                f"{datetime.now(UTC).isoformat()}\t{skill_name}\t{os.environ.get('CLAUDE_SESSION_ID', 'unknown')}\n"
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
