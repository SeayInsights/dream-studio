"""Append-only audit log for hook events.

Writes one JSON object per line to ~/.dream-studio/audit.jsonl.
Call log_event() from each handler's main() with the event type and session ID.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lib.time_utils import utcnow


def log_event(
    event_type: str,
    payload: dict[str, Any],
    session_id: str | None = None,
) -> None:
    audit_path = Path.home() / ".dream-studio" / "audit.jsonl"
    try:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": utcnow().isoformat(),
            "event": event_type,
            "session_id": session_id or "",
            "payload_summary": {k: v for k, v in payload.items() if k == "tool_name" or k == "hook_event_name"},
        }
        with audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass
