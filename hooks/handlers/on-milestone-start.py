#!/usr/bin/env python3
"""Hook: on-milestone-start — write a marker when a DCL command opens a milestone.

Trigger: UserPromptSubmit matching a build/deploy DCL command.
Purpose: Persist a milestone marker to `~/.dream-studio/state/milestone-active.txt`
so `on-milestone-end` (and advisory hooks) can detect an in-flight milestone.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import paths  # noqa: E402

DCL_PATTERN = re.compile(
    r"^(build feature:|build page:|build api:|build component:|build schema:|"
    r"build report:|build app:|build flow:|new game:|3d new game:|3d scene:|"
    r"launch project:|deploy:|python package:|python migrate:|python publish:|"
    r"desktop: build|desktop: phase|desktop: release)",
    re.IGNORECASE,
)

MARKER_FILENAME = "milestone-active.txt"


def read_message() -> str:
    env = os.environ.get("CLAUDE_USER_MESSAGE_TEXT", "").strip()
    if env:
        return env
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return ""
    return str(payload.get("prompt") or payload.get("user_message") or "").strip()


def main() -> None:
    message = read_message()
    if not message or not DCL_PATTERN.match(message):
        return

    marker_path = paths.state_dir() / MARKER_FILENAME
    timestamp = datetime.now(timezone.utc).isoformat()

    if marker_path.exists():
        print(
            f"\n[dream-studio] Milestone already active — skipping duplicate for: {message[:60]}",
            flush=True,
        )
        return

    try:
        marker_path.write_text(
            json.dumps({"command": message, "started_at": timestamp}),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"[on-milestone-start] failed to write marker: {e}", flush=True)
        return

    print(f"\n[dream-studio] Milestone started: {message[:60]}", flush=True)
    print(
        "[dream-studio] Research -> Plan -> Implement required for this milestone:\n"
        "  1. RESEARCH  — read relevant docs, standards, prior decisions (<=3 tool calls)\n"
        "  2. PLAN      — present numbered plan (what changes, what tools, token cost)\n"
        "  3. IMPLEMENT — execute approved plan; stop + re-present if scope changes\n"
        "  Skip only for: read-only queries, single-file edits with a clear target.\n",
        flush=True,
    )


if __name__ == "__main__":
    main()
