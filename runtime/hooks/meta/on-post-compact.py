#!/usr/bin/env python3
"""Hook: on-post-compact — reset context tracking after /compact."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from core.config import paths  # noqa: E402
from core.utils.compact_utils import (  # noqa: E402
    clear_sentinels,
    projects_dir,
    reset_context_bridge,
)


def main() -> None:
    payload: dict = {}
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        pass

    session_id: str | None = payload.get("session_id") or None
    payload_cwd: str | None = payload.get("cwd") or None
    cwd = Path(payload_cwd) if payload_cwd else paths.project_root()

    # Reset bridge file → statusline shows ~0% immediately
    if session_id:
        reset_context_bridge(session_id)

    # Clear sentinels so warnings fire fresh as context grows
    clear_sentinels(projects_dir(cwd), session_id)

    print(
        json.dumps({"status": "ok", "hook": "on-post-compact", "reset": True}),
        flush=True,
    )


if __name__ == "__main__":
    main()
