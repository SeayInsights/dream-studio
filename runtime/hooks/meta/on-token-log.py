#!/usr/bin/env python3
"""Hook: on-token-log — append session token usage to the token log."""

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
        raw = sys.stdin.read().lstrip("﻿")
        data = json.loads(raw) if raw.strip() else {}
        main(data)
    except Exception:
        pass
