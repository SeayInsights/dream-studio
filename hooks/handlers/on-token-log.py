#!/usr/bin/env python3
"""Hook: on-token-log — append session token usage to the token log.

Trigger: Stop (or direct invocation).
Writes a row to `~/.dream-studio/meta/token-log.md` with model and usage
totals. Accepts either pre-extracted tokens on the payload or a
`transcript_path` to parse JSONL lines from.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import paths  # noqa: E402


def extract_usage_from_transcript(transcript_path: str) -> tuple[str, int, int, int]:
    model = "unknown"
    prompt_t = completion_t = 0
    try:
        path = Path(transcript_path)
        if not path.exists():
            return model, 0, 0, 0
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict):
                usage = entry.get("usage") or entry.get("message", {}).get("usage", {})
                if usage:
                    prompt_t += usage.get("input_tokens", 0)
                    completion_t += usage.get("output_tokens", 0)
                m = entry.get("model") or entry.get("message", {}).get("model", "")
                if m and model == "unknown":
                    model = m
    except Exception:
        pass
    return model, prompt_t, completion_t, prompt_t + completion_t


def main(payload: dict) -> None:
    session_name = payload.get("session_name") or payload.get("session_id", "unknown")
    transcript_path = payload.get("transcript_path", "")
    timestamp = payload.get("timestamp", datetime.now(timezone.utc).isoformat())

    if "prompt_tokens" in payload:
        model = payload.get("model", "unknown")
        prompt_t = payload["prompt_tokens"]
        completion_t = payload["completion_tokens"]
        total_t = payload["total_tokens"]
    else:
        model, prompt_t, completion_t, total_t = extract_usage_from_transcript(transcript_path)

    log_path = paths.meta_dir() / "token-log.md"
    row = f"| {timestamp} | {session_name} | {model} | {prompt_t} | {completion_t} | {total_t} |\n"
    try:
        if not log_path.exists():
            log_path.write_text(
                "# Token Log\n\n"
                "| Timestamp | Session | Model | Prompt | Completion | Total |\n"
                "|---|---|---|---|---|---|\n",
                encoding="utf-8",
            )
        with log_path.open("a", encoding="utf-8") as f:
            f.write(row)
    except Exception as e:
        print(f"[on-token-log] failed to write token log: {e}", flush=True)

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
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as e:
        print(json.dumps({"status": "error", "message": str(e)}))
        sys.exit(1)
    main(payload)
