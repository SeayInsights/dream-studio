#!/usr/bin/env python3
"""Session resume: surface the latest unconsumed handoff across all projects.

Runs as a UserPromptSubmit hook (global). On the first user message of a
session, queries SQLite for the latest unconsumed handoff regardless of
which directory the session started in. Prints a briefing so Claude can
pick up where the last session left off.

Uses a sentinel to fire only once per session.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))
from lib.studio_db import (  # noqa: E402
    get_latest_unconsumed_handoff,
    mark_handoff_consumed,
    has_sentinel,
    set_sentinel,
)


def main() -> None:
    session_id = os.environ.get("CLAUDE_SESSION_ID", "unknown")
    sentinel_key = f"resume-shown-{session_id}"
    if has_sentinel(sentinel_key):
        return

    handoff = get_latest_unconsumed_handoff()
    if not handoff:
        set_sentinel(sentinel_key, "resume-check")
        return

    project_id = handoff.get("project_id", "unknown")
    topic = handoff.get("topic", "unknown")
    branch = handoff.get("branch", "unknown")
    last_commit = handoff.get("last_commit", "unknown")
    next_action = handoff.get("next_action", "")
    active_files = handoff.get("active_files") or []
    created = handoff.get("created_at", "")[:19]

    files_str = ""
    if isinstance(active_files, list) and active_files:
        files_str = "\n".join(f"  - {f}" for f in active_files[:5])

    print(
        f"\n[dream-studio] Pending handoff from previous session:\n"
        f"  Project: {project_id}\n"
        f"  Topic:   {topic}\n"
        f"  Branch:  {branch}\n"
        f"  Commit:  {last_commit}\n"
        f"  Created: {created}\n"
        + (f"  Files:\n{files_str}\n" if files_str else "")
        + (f"  Next:    {next_action}\n" if next_action else "")
        + f"\n  To resume, read the handoff file listed above.\n",
        flush=True,
    )

    hsid = handoff.get("session_id")
    if hsid:
        mark_handoff_consumed(hsid)

    set_sentinel(sentinel_key, "resume-check")


if __name__ == "__main__":
    main()
