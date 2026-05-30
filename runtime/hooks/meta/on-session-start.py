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
    update_project_stats,
)  # noqa: E402
from core.sdlc.cwd_resolver import resolve_project_from_cwd  # noqa: E402


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

    # Resolve project_id via .dream-studio-project marker (UUID from business_projects).
    # Returns None for unregistered directories — session records without project attribution
    # are valid (project_id is nullable). Never throws.
    ctx = resolve_project_from_cwd()
    project_id = ctx.project_id if ctx is not None else None
    cwd = str(Path.cwd())

    try:
        insert_session(session_id, project_id)
    except Exception:
        pass
    if project_id is not None:
        try:
            update_project_stats(project_id, sessions_delta=1)
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
        write_session_config(
            session_id,
            {
                "session_id": session_id,
                "invocation_flags": flags,
                "cwd": cwd,
                "timestamp": int(time.time()),
                "continuation_count": 0,
            },
        )
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
