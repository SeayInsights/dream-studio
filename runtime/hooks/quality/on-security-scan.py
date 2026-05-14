#!/usr/bin/env python3
"""Hook: on-security-scan — lightweight security pattern check on Edit/Write.

Trigger: PostToolUse (Edit|Write).
Scans new content for high-signal security anti-patterns and prints a warning.
Advisory only — never blocks.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from control.analysis import security_patterns  # noqa: E402


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return

    tool_name = payload.get("tool_name", "")
    if tool_name not in ("Edit", "Write"):
        return

    file_path, content = security_patterns.extract_content(payload)
    if not content or not security_patterns.should_scan(file_path):
        return

    findings = security_patterns.scan_for_patterns(content)
    if findings:
        security_patterns.print_warning(file_path, findings)


if __name__ == "__main__":
    main()
