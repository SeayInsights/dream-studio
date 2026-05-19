#!/usr/bin/env python3
"""Hook: on-game-validate — validate game project files on Edit|Write."""

import json
import os
import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[3]
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from control.context import pack as pack_context  # noqa: E402
from runtime.lib.domains import game_validate_orchestrator  # noqa: E402


def main() -> None:
    if not pack_context.is_pack_active("domains"):
        return

    try:
        raw = sys.stdin.read().lstrip("﻿")
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    file_path_str = os.environ.get("CLAUDE_FILE_PATH", "").strip()
    if not file_path_str:
        tool_input = payload.get("tool_input", {})
        if isinstance(tool_input, str):
            try:
                tool_input = json.loads(tool_input)
            except Exception:
                tool_input = {}
        file_path_str = tool_input.get("file_path", "")
    if not file_path_str:
        return

    result = game_validate_orchestrator.validate_and_format(Path(file_path_str))
    if result:
        print(result.output, flush=True)
        if result.should_block:
            sys.exit(2)


if __name__ == "__main__":
    main()
