#!/usr/bin/env python3
"""Hook: on-security-scan — lightweight security pattern check on Edit/Write.

Trigger: PostToolUse (Edit|Write).
Scans new content for high-signal security anti-patterns and prints a warning.
Advisory only — never blocks.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_PATTERNS = [
    (re.compile(r'(?i)(password|passwd|api_key|api_secret|secret_key|auth_token)\s*=\s*["\'][^"\']{4,}["\']'), "hardcoded credential"),
    (re.compile(r'\beval\s*\('), "eval()"),
    (re.compile(r'\bos\.system\s*\('), "os.system()"),
    (re.compile(r'subprocess[^\n]+shell\s*=\s*True'), "shell=True in subprocess"),
    (re.compile(r'(?i)-----BEGIN\s+(RSA|EC|DSA|PRIVATE)\s+KEY-----'), "private key in source"),
    (re.compile(r'(?i)(ghp_|sk-|AKIA)[A-Za-z0-9]{10,}'), "token-shaped string"),
]

_SCAN_EXTS = {".py", ".ts", ".js", ".tsx", ".jsx", ".sh", ".yaml", ".yml", ".env"}
_SKIP_PATH_PARTS = {"tests", "test", "__pycache__", "node_modules", ".venv", "venv"}


def _content(tool_name: str, tool_input: dict) -> tuple[str, str]:
    fp = tool_input.get("file_path", "")
    if tool_name == "Edit":
        return fp, tool_input.get("new_string", "")
    if tool_name == "Write":
        return fp, tool_input.get("content", "")
    return fp, ""


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return

    tool_name = payload.get("tool_name", "")
    if tool_name not in ("Edit", "Write"):
        return

    tool_input = payload.get("tool_input", {})
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except Exception:
            return

    fp, content = _content(tool_name, tool_input)
    if not content:
        return

    if fp:
        p = Path(fp)
        if p.suffix.lower() not in _SCAN_EXTS:
            return
        if _SKIP_PATH_PARTS & set(p.parts):
            return

    findings = [label for pattern, label in _PATTERNS if pattern.search(content)]
    if findings:
        name = Path(fp).name if fp else "file"
        labels = ", ".join(findings)
        print(f"\n[dream-studio] Security: {name} — {labels}. Review before committing.\n", flush=True)


if __name__ == "__main__":
    main()
