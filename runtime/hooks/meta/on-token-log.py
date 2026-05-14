#!/usr/bin/env python3
"""Hook: on-token-log — append session token usage to the token log."""

import json, sys
from pathlib import Path
from core.config import paths
from core.utils.time import utcnow
from core.telemetry.token_logger import extract_usage_from_transcript, write_token_log


def main(payload: dict) -> None:
    session_name = payload.get("session_name") or payload.get("session_id", "unknown")
    timestamp = payload.get("timestamp", utcnow().isoformat())

    if "prompt_tokens" in payload:
        model, prompt_t, completion_t, total_t = (
            payload.get("model", "unknown"),
            payload["prompt_tokens"],
            payload["completion_tokens"],
            payload["total_tokens"],
        )
    else:
        model, prompt_t, completion_t, total_t = extract_usage_from_transcript(
            payload.get("transcript_path", "")
        )

    write_token_log(
        paths.meta_dir() / "token-log.md",
        timestamp,
        session_name,
        model,
        prompt_t,
        completion_t,
        total_t,
        payload.get("hook_output_bytes", 0),
        payload.get("hook_overhead_est", 0),
    )

    print(
        json.dumps(
            {
                "status": "ok",
                "hook": "on-token-log",
                "session_name": session_name,
                "model": model,
                "total_tokens": total_t,
            }
        )
    )


if __name__ == "__main__":
    try:
        data = json.loads(raw) if (raw := sys.stdin.read()).strip() else {}
        main(data)
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}))
        sys.exit(1)
