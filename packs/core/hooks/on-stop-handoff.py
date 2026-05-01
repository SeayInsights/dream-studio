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

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hooks"))

from lib import paths  # noqa: E402
from lib.context_handoff import active_files, write_handoff, write_recap  # noqa: E402
from lib.models import StopPayload  # noqa: E402
from lib.studio_db import (  # noqa: E402
    set_sentinel, has_sentinel,
    upsert_project, insert_session, insert_handoff,
)


_SESSION_END_KB = 0.0  # sentinel: Stop hook has no context % — use 0 KB


def _last_commit_age_seconds(cwd: Path) -> float | None:
    """Return seconds since the last commit, or None if git is unavailable."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ct"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=4,
        )
        ts = result.stdout.strip()
        if not ts:
            return None
        return time.time() - float(ts)
    except Exception:
        return None


def _has_activity(cwd: Path) -> bool:
    """Return True if the working tree has changes OR a recent commit exists."""
    files = active_files(cwd)
    if files:
        return True
    age = _last_commit_age_seconds(cwd)
    if age is not None and age <= 86400:  # 24 hours
        return True
    return False


def main() -> None:
    session_id: str | None = None
    payload_cwd: str | None = None

    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        try:
            validated = StopPayload(**payload)
            session_id = validated.session_id or None
        except Exception:
            session_id = payload.get("session_id") or None
        payload_cwd = payload.get("cwd") or None
    except Exception:
        pass

    cwd = Path(payload_cwd) if payload_cwd else paths.project_root()

    if not _has_activity(cwd):
        return

    key = f"handoff-done-{session_id or 'unknown'}"
    if has_sentinel(key):
        return

    handoff_path = write_handoff(cwd, _SESSION_END_KB, session_id, is_pct=False)
    write_recap(cwd, _SESSION_END_KB, session_id, handoff_path)

    try:
        project_id = cwd.name
        sid = session_id or "unknown"
        branch = subprocess.run(
            ["git", "branch", "--show-current"], cwd=cwd,
            capture_output=True, text=True, timeout=5,
        ).stdout.strip() or "unknown"
        last_commit = subprocess.run(
            ["git", "log", "--oneline", "-1"], cwd=cwd,
            capture_output=True, text=True, timeout=5,
        ).stdout.strip() or "unknown"
        upsert_project(project_id, str(cwd))
        insert_session(sid, project_id)
        insert_handoff(
            sid, project_id, branch,
            branch=branch,
            last_commit=last_commit,
            active_files=[str(handoff_path)] if handoff_path else None,
            next_action=f"Read {handoff_path} to resume.",
        )
    except Exception:
        pass

    set_sentinel(key, "handoff-done")


if __name__ == "__main__":
    main()
