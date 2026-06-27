#!/usr/bin/env python3
"""Hook: on-session-end — close out the session row on Stop event."""

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

from core.event_store.studio_db import end_session, has_sentinel, set_sentinel


def main() -> None:
    try:
        payload = json.loads(raw) if (raw := sys.stdin.read()).strip() else {}
    except Exception:
        payload = {}

    if not (session_id := payload.get("session_id", "")):
        return

    sentinel_key = f"session-ended-{session_id}"
    if has_sentinel(sentinel_key):
        return

    input_tokens = payload.get("prompt_tokens") if "prompt_tokens" in payload else None
    output_tokens = payload.get("completion_tokens") if "completion_tokens" in payload else None
    outcome = payload.get("stop_reason") or "end_turn"

    try:
        end_session(
            session_id, outcome=outcome, input_tokens=input_tokens, output_tokens=output_tokens
        )
    except Exception:
        pass

    # validate_session_research removed — raw_research dropped migration 131

    try:
        set_sentinel(sentinel_key, "session")
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
