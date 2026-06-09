#!/usr/bin/env python3
"""Hook: on-skill-telemetry — capture skill telemetry at session end."""

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

from core.config import paths
from core.telemetry.processor import detect_success, get_session_skills, write_telemetry


def main() -> None:
    try:
        payload = json.loads(raw) if (raw := sys.stdin.read()).strip() else {}
    except Exception:
        return
    session_id = payload.get("session_id", "")
    state_dir = paths.state_dir()
    skills = get_session_skills(state_dir / "skill-usage.jsonl", session_id)
    if skills:
        write_telemetry(state_dir / "telemetry-buffer.jsonl", skills, detect_success(payload))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
