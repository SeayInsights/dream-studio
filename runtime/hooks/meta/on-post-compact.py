#!/usr/bin/env python3
"""Hook: on-post-compact — reset context tracking after /compact."""

from __future__ import annotations

import json
import os
import sys
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

from core.config import paths  # noqa: E402
from core.utils.compact_utils import (  # noqa: E402
    clear_sentinels,
    projects_dir,
    reset_context_bridge,
)


def main() -> None:
    payload: dict = {}
    try:
        raw = sys.stdin.read().lstrip("﻿")
        payload = json.loads(raw) if raw.strip() else {}
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
