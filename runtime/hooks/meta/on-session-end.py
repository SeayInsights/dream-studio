#!/usr/bin/env python3
"""Hook: on-session-end — close out the session row on Stop event."""

import json
import sys
from pathlib import Path

from control.session.manager import validate_session_research
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
    output_tokens = payload.get("completion_tokens") if "prompt_tokens" in payload else None

    try:
        end_session(session_id, input_tokens=input_tokens, output_tokens=output_tokens)
    except Exception:
        pass

    try:
        validate_session_research(session_id)
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
