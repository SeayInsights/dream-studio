#!/usr/bin/env python3
"""Hook: on-post-compact — reset context tracking immediately after /compact completes.

Trigger: PostCompact.
Writes used_pct=0 to the statusline bridge file so the status bar reflects the
compacted context right away, without waiting for the next user prompt.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hooks"))

from lib import paths  # noqa: E402


def _projects_dir(cwd: Path) -> Path:
    override = os.environ.get("CLAUDE_PROJECTS_DIR")
    if override:
        return Path(override)
    s = str(cwd).replace("\\", "/")
    if len(s) >= 2 and s[1] == ":":
        slug = s[0].upper() + "-" + s[2:]
    else:
        slug = s
    cleaned = ""
    for ch in slug:
        if ch.isascii() and (ch.isalnum() or ch in "-_."):
            cleaned += ch
        elif ch in ":\\/  ":
            cleaned += "-"
        else:
            cleaned += f"-u{ord(ch):04x}-"
    return Path.home() / ".claude" / "projects" / cleaned[:200]


def _sentinel(projects: Path, session_id: str | None, label: str) -> Path:
    return projects / f".{label}-sentinel-{session_id or 'unknown'}"


def main() -> None:
    payload: dict = {}
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        pass

    session_id: str | None = payload.get("session_id") or None
    payload_cwd: str | None = payload.get("cwd") or None
    cwd = Path(payload_cwd) if payload_cwd else paths.project_root()

    # Reset bridge file → statusline shows ~0% immediately after compact
    if session_id:
        bp = Path(tempfile.gettempdir()) / f"claude-ctx-{session_id}.json"
        try:
            bp.write_text(json.dumps({
                "session_id": session_id,
                "used_pct": 0.0,
                "raw_pct": 0.0,
                "remaining_percentage": 100.0,
                "timestamp": int(time.time()),
                "post_compact": True,
            }), encoding="utf-8")
        except Exception:
            pass

    # Clear sentinels so threshold warnings fire fresh as context grows again
    projects = _projects_dir(cwd)
    for label in ("handoff", "compact", "compact-msg", "compact-cooldown", "warn-pct"):
        try:
            _sentinel(projects, session_id, label).unlink(missing_ok=True)
        except Exception:
            pass

    print(
        json.dumps({"status": "ok", "hook": "on-post-compact", "reset": True}),
        flush=True,
    )


if __name__ == "__main__":
    main()
