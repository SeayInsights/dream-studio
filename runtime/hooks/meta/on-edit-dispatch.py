#!/usr/bin/env python3
"""Dispatcher: PostToolUse Edit|Write — single process for all edit/write hooks.

Replaces 4 subprocess invocations with one process that imports and calls
each handler sequentially. Reads stdin once and re-injects it before each
handler's main() so existing code works unchanged.

Handlers (in order):
  1. on-agent-correction (runtime/hooks/quality)
  2. on-game-validate    (runtime/hooks/domains)
  3. on-security-scan    (runtime/hooks/quality)
  4. on-structure-check  (runtime/hooks/quality)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _get_plugin_root() -> Path:
    sidecar = Path(__file__).resolve()
    for _ in range(6):
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


PLUGIN_ROOT = _get_plugin_root()
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))
sys.path.insert(0, str(PLUGIN_ROOT / "hooks"))

from control.execution.dispatch_tracking import run_handlers  # noqa: E402

HANDLERS = [
    (
        "on-agent-correction",
        PLUGIN_ROOT / "runtime" / "hooks" / "quality" / "on-agent-correction.py",
    ),
    ("on-game-validate", PLUGIN_ROOT / "runtime" / "hooks" / "domains" / "on-game-validate.py"),
    ("on-security-scan", PLUGIN_ROOT / "runtime" / "hooks" / "quality" / "on-security-scan.py"),
    ("on-structure-check", PLUGIN_ROOT / "runtime" / "hooks" / "quality" / "on-structure-check.py"),
]

STATE_DIR = Path.home() / ".dream-studio" / "state"

PROTECTED_PATHS = [
    "settings.json",
    "settings.local.json",
    "CLAUDE.md",
]


def main() -> None:
    raw_payload = sys.stdin.read()

    try:
        data = json.loads(raw_payload) if raw_payload.strip() else {}
    except Exception:
        data = {}

    tool_input = data.get("tool_input") or {}
    file_path = (tool_input.get("file_path") or tool_input.get("path") or "").replace("\\", "/")

    if any(p in file_path for p in PROTECTED_PATHS):
        sys.exit(0)

    is_operator = os.environ.get("DREAM_STUDIO_OPERATOR_SESSION", "").lower() in (
        "1",
        "true",
        "yes",
    )
    _check_rubric_guardrail(file_path, event_id=data.get("event_id"), is_operator=is_operator)

    run_handlers(HANDLERS, raw_payload, "PostToolUse_Edit_Write", STATE_DIR)


def _check_rubric_guardrail(
    file_path: str, event_id: str | None = None, *, is_operator: bool = False
) -> None:
    """Call check_rubric_write_guardrail for Write/Edit events. Non-fatal."""
    try:
        import sqlite3

        from guardrails.evaluator import check_rubric_write_guardrail

        db_path = STATE_DIR / "studio.db"
        conn = sqlite3.connect(str(db_path))
        decision = check_rubric_write_guardrail(
            file_path, conn=conn, event_id=event_id, is_operator=is_operator
        )
        conn.close()
        if decision is not None:
            print(
                f"\n[guardrails] BLOCK: {decision.message}",
                file=sys.stderr,
            )
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
