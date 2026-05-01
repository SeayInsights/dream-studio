#!/usr/bin/env python3
"""Hook: on-session-start — record a new session row on first user prompt.

Trigger: UserPromptSubmit (fires on every prompt; sentinel ensures single fire).

Detects session_id from the payload or CLAUDE_SESSION_ID env var; generates
a UUID as fallback. Calls insert_session() to persist a row in raw_sessions
and upsert_project() to ensure the project is registered.

Exits 0 always — tracking failure must never block a session.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hooks"))

from lib.studio_db import (  # noqa: E402
    has_sentinel,
    insert_session,
    set_sentinel,
    upsert_project,
)


def main() -> None:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    session_id = (
        payload.get("session_id")
        or os.environ.get("CLAUDE_SESSION_ID")
        or str(uuid.uuid4())
    )

    sentinel_key = f"session-started-{session_id}"
    if has_sentinel(sentinel_key):
        return

    project_id = Path.cwd().name

    try:
        upsert_project(project_id, str(Path.cwd()))
    except Exception:
        pass

    try:
        insert_session(session_id, project_id)
    except Exception:
        pass

    try:
        set_sentinel(sentinel_key, "session")
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
