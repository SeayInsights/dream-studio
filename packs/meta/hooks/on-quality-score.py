#!/usr/bin/env python3
"""Hook: on-quality-score — capture skill telemetry at session end.

Trigger: Stop event.
Reads skill invocations for this session from skill-usage.jsonl, applies
a success heuristic against any assistant messages in the payload, and
appends one JSONL record per skill to telemetry-buffer.jsonl.
Exits 0 always — telemetry failure must never block session end.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hooks"))
from lib import paths  # noqa: E402

_FAIL_WORDS = frozenset(["error", "traceback", "failed", "exception", "cannot", "unable to", "not found"])


def _detect_success(payload: dict) -> bool:
    """Heuristic: scan last assistant message for failure keywords."""
    for msg in reversed(payload.get("messages") or []):
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        text = content if isinstance(content, str) else " ".join(
            c.get("text", "") for c in content if isinstance(c, dict)
        )
        if text:
            lower = text.lower()
            return not any(w in lower for w in _FAIL_WORDS)
    return True  # no assistant message → assume success


def main() -> None:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return

    session_id = payload.get("session_id", "")
    state_dir = paths.state_dir()

    usage_path = state_dir / "skill-usage.jsonl"
    if not usage_path.is_file():
        return

    try:
        records = [json.loads(ln) for ln in usage_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except Exception:
        return

    seen: set[str] = set()
    session_skills = []
    for r in records:
        if r.get("session") == session_id:
            name = r.get("skill", "unknown")
            if name not in seen:
                seen.add(name)
                session_skills.append({"name": name, "ts": r.get("ts", "")})

    if not session_skills:
        return

    success = 1 if _detect_success(payload) else 0
    now = datetime.now(timezone.utc).isoformat()

    buf_path = state_dir / "telemetry-buffer.jsonl"
    try:
        with buf_path.open("a", encoding="utf-8") as f:
            for skill in session_skills:
                f.write(json.dumps({
                    "skill_name": skill["name"],
                    "invoked_at": skill["ts"] or now,
                    "success": success,
                }) + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
