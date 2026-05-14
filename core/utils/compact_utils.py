"""Utilities for compact/context management hooks."""

from __future__ import annotations

import os
from pathlib import Path


def projects_dir(cwd: Path) -> Path:
    """Get the project-specific directory for sentinels and state."""
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


def sentinel_path(projects: Path, session_id: str | None, label: str) -> Path:
    """Get path to a sentinel file for the given session and label."""
    return projects / f".{label}-sentinel-{session_id or 'unknown'}"


def reset_context_bridge(session_id: str) -> None:
    """Reset the context bridge file to show 0% usage after compact."""
    import json
    import tempfile
    import time

    bp = Path(tempfile.gettempdir()) / f"claude-ctx-{session_id}.json"
    try:
        bp.write_text(
            json.dumps(
                {
                    "session_id": session_id,
                    "used_pct": 0.0,
                    "raw_pct": 0.0,
                    "remaining_percentage": 100.0,
                    "timestamp": int(time.time()),
                    "post_compact": True,
                }
            ),
            encoding="utf-8",
        )
    except Exception:
        pass


def clear_sentinels(projects: Path, session_id: str | None) -> None:
    """Clear sentinel files so warnings can fire fresh."""
    labels = ("handoff", "compact", "compact-msg", "compact-cooldown", "warn-pct")
    for label in labels:
        try:
            sentinel_path(projects, session_id, label).unlink(missing_ok=True)
        except Exception:
            pass
