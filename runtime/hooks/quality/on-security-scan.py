#!/usr/bin/env python3
"""Hook: on-security-scan — lightweight security pattern check on Edit/Write.

Trigger: PostToolUse (Edit|Write), via runtime/hooks/meta/on-edit-dispatch.py.

Scans THE FILE that was just written, not the payload fragment. It used to scan an Edit's
`new_string` — the replacement text — which for a realistic payload is something like
`'    shell=True,'`: unparseable as Python, so the parse-based detection cannot run on it,
and missing the `subprocess` token the old regex also required. Being PostToolUse, the
complete file is already on disk here, so reading it costs one stat and one read and gives
the checker something it can actually parse. The fragment remains the fallback for a path
that cannot be read.

ADVISORY BY CONSTRUCTION, not by choice: PostToolUse runs after the edit is applied, so
there is nothing left to block. The blocking tier is `core/gates/security_scan.py`, which
runs over changed FILES in the pre-push chain — and which is the only tier that can see a
file written by a patch script, a merge or a rebase, none of which fire an Edit/Write hook
at all.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from control.analysis import security_patterns  # noqa: E402


def main() -> None:
    try:
        raw = sys.stdin.read().lstrip("﻿")
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return

    tool_name = payload.get("tool_name", "")
    if tool_name not in ("Edit", "Write"):
        return

    file_path, fragment = security_patterns.extract_content(payload)
    if not security_patterns.should_scan(file_path):
        return

    # THE FILE, not the fragment. PostToolUse means the write has landed, so this is the
    # content that now exists -- and unlike a replacement fragment it parses.
    content = ""
    try:
        content = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        content = fragment or ""
    if not content:
        return

    findings = security_patterns.scan_for_patterns(content, file_path)
    if findings:
        security_patterns.print_warning(file_path, findings)


if __name__ == "__main__":
    main()
