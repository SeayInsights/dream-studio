#!/usr/bin/env python3
"""Hook: on-stop-handoff — write a handoff + recap on natural session Stop.

Trigger: Stop event.
Only writes if there is actual git activity: working tree has changes OR a
commit was made in the last 24 hours. Skips silently when the session was idle.

Uses is_pct=False with kb=0 as a sentinel — the Stop event has no context %
available. The handoff labels this as a "session end" (not a threshold trigger).
Must complete in < 2 seconds.
"""

from __future__ import annotations

import sys
from pathlib import Path

from core.config import paths
from control.context import handoff as context_handoff  # noqa: E402
from core.event_store.studio_db import set_sentinel, has_sentinel  # noqa: E402


def main() -> None:
    session_id, cwd = context_handoff.parse_stop_payload(sys.stdin.read(), paths.project_root())

    if not context_handoff.has_session_activity(cwd):
        return

    key = f"handoff-done-{session_id or 'unknown'}"
    if has_sentinel(key):
        return

    handoff_path = context_handoff.write_session_handoff(cwd, session_id)
    context_handoff.record_session_to_db(cwd, session_id, handoff_path)

    set_sentinel(key, "handoff-done")


if __name__ == "__main__":
    main()
