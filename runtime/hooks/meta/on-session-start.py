#!/usr/bin/env python3
"""Hook: on-session-start — record new session on first user prompt."""

import json
import os
import sys
import time
import uuid
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

# --- resolve session_config via installed layout ---
_meta_dir = Path(__file__).parent
_runtime_dir = _meta_dir.parent.parent  # ~/.claude/hooks/runtime/
if str(_runtime_dir) not in sys.path:
    sys.path.insert(0, str(_runtime_dir))

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
    cwd = str(Path.cwd())
    try:
        upsert_project(project_id, cwd)
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

    # --- write session config for continuation spawner ---
    try:
        from session_config import detect_invocation_flags, write_session_config
        flags = detect_invocation_flags()
        write_session_config(session_id, {
            "session_id": session_id,
            "invocation_flags": flags,
            "cwd": cwd,
            "timestamp": int(time.time()),
            "continuation_count": 0,
        })
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
