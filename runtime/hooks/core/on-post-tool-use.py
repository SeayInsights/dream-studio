#!/usr/bin/env python3
"""Hook shim: PostToolUse — token attribution capture.

Thin shim. Reads stdin, delegates to core.telemetry.token_capture, exits 0.
Last-resort failure logging if the module import or call fails.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
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
    return Path(__file__).resolve().parents[3]


_PLUGIN_ROOT = _get_plugin_root()
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))


def _emergency_log(error: str, payload_raw: str) -> None:
    """Last-resort logger. Bare minimum code path; almost never can fail."""
    try:
        log_dir = Path.home() / ".dream-studio" / "state" / "diagnostics"
        override = os.environ.get("DS_DIAGNOSTICS_DIR")
        if override:
            log_dir = Path(override)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "hook-failures.jsonl"
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "category": "failure",
            "source": "on-post-tool-use.shim",
            "details": {
                "error": error,
                "payload_raw_truncated": payload_raw[:500],
            },
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # absolutely never raise from the shim


def main() -> int:
    payload_raw = ""
    try:
        payload_raw = sys.stdin.read()
        payload = json.loads(payload_raw) if payload_raw.strip() else {}
        from core.telemetry.token_capture import handle_post_tool_use

        handle_post_tool_use(payload)
    except Exception as e:
        _emergency_log(f"{type(e).__name__}: {e}", payload_raw)
    return 0


if __name__ == "__main__":
    sys.exit(main())
