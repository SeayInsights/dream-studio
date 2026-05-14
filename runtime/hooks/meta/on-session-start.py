#!/usr/bin/env python3
"""Hook: on-session-start — record new session on first user prompt."""

import json
import os
import sys
import uuid
from pathlib import Path
from core.event_store.studio_db import (
    has_sentinel,
    insert_session,
    set_sentinel,
    upsert_project,
)  # noqa: E402


def main() -> None:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}
    session_id = (
        payload.get("session_id") or os.environ.get("CLAUDE_SESSION_ID") or str(uuid.uuid4())
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
