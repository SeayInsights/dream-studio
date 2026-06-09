#!/usr/bin/env python3
"""Hook: on-structure-check — nudge when source files are placed outside standard dirs.

Trigger: PostToolUse (Write only — creating new files).
Checks FSC conventions: .py/.ts/.js source files should live in src/, lib/, hooks/,
app/, or tests/ — not scattered at the project root. Advisory only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from core.config import paths  # noqa: E402
from core.validation import structure as structure_rules  # noqa: E402


def main() -> None:
    try:
        raw = sys.stdin.read().lstrip("﻿")
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return

    if payload.get("tool_name") != "Write":
        return

    file_path = structure_rules.extract_file_path(payload)
    if not file_path or not structure_rules.is_source_file(file_path):
        return

    violation = structure_rules.check_structure_violation(file_path)
    if violation:
        structure_rules.emit_nudge_once(violation, file_path, paths.state_dir())


if __name__ == "__main__":
    main()
