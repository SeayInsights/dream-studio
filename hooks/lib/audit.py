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
    effectiveness_score: float | None = None,
) -> None:
    """Append one audit record to ~/.dream-studio/audit.jsonl.

    Args:
        event_type: Hook or event name (e.g. "on-pulse", "on-game-validate").
        payload: Raw hook payload — only summary fields are stored.
        session_id: Optional session identifier for correlation.
        effectiveness_score: Optional 0.0–1.0 score set when a hook's output
            is known to have influenced user behaviour within 2 turns.
            None means "not yet measured".
    """
    audit_path = Path.home() / ".dream-studio" / "audit.jsonl"
    try:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        record: dict[str, Any] = {
            "ts": utcnow().isoformat(),
            "event": event_type,
            "session_id": session_id or "",
            "payload_summary": {k: v for k, v in payload.items() if k in ("tool_name", "hook_event_name")},
        }
        if effectiveness_score is not None:
            record["effectiveness_score"] = effectiveness_score
        with audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass
