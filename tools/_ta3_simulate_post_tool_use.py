#!/usr/bin/env python3
"""TA3 end-to-end verification: simulate a PostToolUse hook payload.

Constructs a realistic PostToolUse payload, pipes it to the hook shim, then
verifies the token.consumed event landed in canonical_events.

Usage:
    py tools/_ta3_simulate_post_tool_use.py

Exit codes:
    0 — all assertions passed
    1 — one or more assertions failed
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK_SHIM = REPO_ROOT / "runtime" / "hooks" / "core" / "on-post-tool-use.py"
DS_HOME = Path.home() / ".dream-studio"
STATE_DIR = DS_HOME / "state"
DB_PATH = STATE_DIR / "studio.db"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _ingest_spool() -> None:
    """Flush pending spool events into canonical_events (in-process, no subprocess)."""
    try:
        from spool.config import get_spool_root
        from spool.ingestor import ingest_pending

        spool_root = get_spool_root()
        ingest_pending(root=spool_root, db_path=DB_PATH)
    except Exception as exc:
        print(f"  [WARN] spool ingest error: {exc}")


def _run_hook(payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK_SHIM)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=30,
    )


def _check(label: str, condition: bool) -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}")
    return condition


def main() -> int:
    print("TA3 end-to-end simulation")
    print(f"  Hook shim: {HOOK_SHIM}")
    print(f"  DB:        {DB_PATH}")
    print()

    if not HOOK_SHIM.exists():
        print("  [FAIL] Hook shim not found")
        return 1

    if not DB_PATH.exists():
        print("  [WARN] DB not found — canonical_events check will be skipped")
        can_check_db = False
    else:
        can_check_db = True

    # Build a realistic PostToolUse payload.
    tool_use_id = f"toolu_{uuid.uuid4().hex[:8]}"
    session_id = f"sess_{uuid.uuid4().hex[:8]}"
    payload = {
        "tool_name": "Read",
        "tool_use_id": tool_use_id,
        "tool_input": {"file_path": "some/relative/path.py"},
        "tool_response": "file contents here (redacted in production)",
        "is_error": False,
        "session_id": session_id,
        "model": "claude-sonnet-4-6",
        "usage": {
            "input_tokens": 1234,
            "output_tokens": 567,
            "cache_creation_input_tokens": 100,
            "cache_read_input_tokens": 50,
        },
    }

    print("Firing hook shim with simulated PostToolUse payload...")
    t0 = time.monotonic()
    result = _run_hook(payload)
    elapsed_ms = (time.monotonic() - t0) * 1000
    print(f"  Hook completed in {elapsed_ms:.0f}ms")

    all_pass = True
    all_pass &= _check("Hook shim exits 0", result.returncode == 0)

    if can_check_db:
        # Give ingestor a moment to flush, then ingest.
        time.sleep(0.5)
        print("  Ingesting spool...")
        _ingest_spool()
        time.sleep(0.3)

        conn = sqlite3.connect(str(DB_PATH))
        try:
            rows = conn.execute(
                "SELECT trace, payload FROM canonical_events"
                " WHERE event_type = 'token.consumed'"
                " ORDER BY rowid DESC LIMIT 5",
            ).fetchall()
        finally:
            conn.close()

        all_pass &= _check("At least one token.consumed event in canonical_events", len(rows) > 0)

        if rows:
            trace = json.loads(rows[0][0])
            evt_payload = json.loads(rows[0][1])

            all_pass &= _check("trace.domain == telemetry", trace.get("domain") == "telemetry")
            all_pass &= _check(
                "trace.attribution_status is set",
                trace.get("attribution_status") in ("fully_attributed", "partial", "orphan"),
            )
            all_pass &= _check("trace.tool_name == Read", trace.get("tool_name") == "Read")
            all_pass &= _check("trace.machine_id is set", bool(trace.get("machine_id")))
            all_pass &= _check(
                "payload.input_tokens == 1234", evt_payload.get("input_tokens") == 1234
            )
            all_pass &= _check(
                "payload.output_tokens == 567", evt_payload.get("output_tokens") == 567
            )
            all_pass &= _check(
                "payload.granularity == tool_invocation",
                evt_payload.get("granularity") == "tool_invocation",
            )
            all_pass &= _check(
                "payload.cache_creation_input_tokens == 100",
                evt_payload.get("cache_creation_input_tokens") == 100,
            )

            # No absolute paths must appear in the event.
            event_str = json.dumps({"trace": trace, "payload": evt_payload})
            user_home = str(Path.home()).replace("\\", "/")
            all_pass &= _check("No absolute home path in event", user_home not in event_str)
    else:
        print("  [SKIP] DB checks skipped (DB not found)")

    print()
    if all_pass:
        print("All checks passed.")
    else:
        print("One or more checks FAILED.")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
