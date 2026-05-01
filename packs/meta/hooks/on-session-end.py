#!/usr/bin/env python3
"""Hook: on-session-end — close out the session row on Stop event.

Trigger: Stop (fires before on-stop-handoff so session is ended first).

Reads session_id from the Stop payload. Calls end_session() to set
ended_at, duration_s, and token totals if present in the payload.
A sentinel prevents double-firing if Stop fires more than once.

Exits 0 always — tracking failure must never block session end.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hooks"))

from lib.studio_db import end_session, has_sentinel, set_sentinel  # noqa: E402


def main() -> None:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    session_id = payload.get("session_id", "")
    if not session_id:
        return

    sentinel_key = f"session-ended-{session_id}"
    if has_sentinel(sentinel_key):
        return

    input_tokens: int | None = None
    output_tokens: int | None = None
    if "prompt_tokens" in payload:
        input_tokens = payload.get("prompt_tokens")
        output_tokens = payload.get("completion_tokens")

    try:
        end_session(
            session_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
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
