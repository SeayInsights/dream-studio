#!/usr/bin/env python3
"""Hook: on-skill-telemetry — capture skill telemetry at session end."""

import json, sys
from pathlib import Path
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
