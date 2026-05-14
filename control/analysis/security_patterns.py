"""Security pattern scanning library for on-security-scan hook.

Extracts security anti-pattern detection logic from hook to comply with
constitutional requirement that hooks be <50 lines.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

PATTERNS = [
    (
        re.compile(
            r'(?i)(password|passwd|api_key|api_secret|secret_key|auth_token)\s*=\s*["\'][^"\']{4,}["\']'
        ),
        "hardcoded credential",
    ),
    (re.compile(r"\beval\s*\("), "eval()"),
    (re.compile(r"\bos\.system\s*\("), "os.system()"),
    (re.compile(r"subprocess[^\n]+shell\s*=\s*True"), "shell=True in subprocess"),
    (re.compile(r"(?i)-----BEGIN\s+(RSA|EC|DSA|PRIVATE)\s+KEY-----"), "private key in source"),
    (re.compile(r"(?i)(ghp_|sk-|AKIA)[A-Za-z0-9]{10,}"), "token-shaped string"),
]

SCAN_EXTS = {".py", ".ts", ".js", ".tsx", ".jsx", ".sh", ".yaml", ".yml", ".env"}
SKIP_PATH_PARTS = {"tests", "test", "__pycache__", "node_modules", ".venv", "venv"}


def extract_content(payload: dict) -> tuple[str, str]:
    """Extract file path and content from tool payload.

    Returns:
        (file_path, content) tuple. Content is empty string if not Edit/Write.
    """
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})

    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except Exception:
            return "", ""

    fp = tool_input.get("file_path", "")

    if tool_name == "Edit":
        return fp, tool_input.get("new_string", "")
    if tool_name == "Write":
        return fp, tool_input.get("content", "")

    return fp, ""


def should_scan(file_path: str) -> bool:
    """Check if file should be scanned based on extension and path.

    Args:
        file_path: Path to file being written/edited

    Returns:
        True if file should be scanned, False otherwise
    """
    if not file_path:
        return False

    p = Path(file_path)

    # Check extension
    if p.suffix.lower() not in SCAN_EXTS:
        return False

    # Check if path contains skip parts
    if SKIP_PATH_PARTS & set(p.parts):
        return False

    return True


def scan_for_patterns(content: str) -> list[str]:
    """Scan content for security anti-patterns.

    Args:
        content: File content to scan

    Returns:
        List of pattern labels that matched. Empty list if no matches.
    """
    return [label for pattern, label in PATTERNS if pattern.search(content)]


def print_warning(file_path: str, findings: list[str]) -> None:
    """Print security warning for findings.

    Args:
        file_path: Path to file with findings
        findings: List of pattern labels that matched
    """
    name = Path(file_path).name if file_path else "file"
    labels = ", ".join(findings)
    print(f"\n[dream-studio] Security: {name} — {labels}. Review before committing.\n", flush=True)
