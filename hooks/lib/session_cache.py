"""
session_cache.py — Read session files from a session directory and output to stdout.

CLI:
    py hooks/lib/session_cache.py --session-dir <path> --query <filename|*|all>

Module API:
    read_session_file(session_dir, filename) -> str
    read_all_session_files(session_dir) -> str
"""

import argparse
import sys
from pathlib import Path

ALLOWED_EXTENSIONS = {".md", ".json", ".yaml", ".yml", ".txt"}


def read_session_file(session_dir: str, filename: str) -> str:
    """Return the contents of <filename> inside <session_dir>, or empty string."""
    base = Path(session_dir)
    if not base.is_dir():
        return ""
    target = base / filename
    if not target.is_file():
        return ""
    if target.suffix.lower() not in ALLOWED_EXTENSIONS:
        return ""
    try:
        return target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def read_all_session_files(session_dir: str) -> str:
    """Return all allowed files in <session_dir> concatenated with separators."""
    base = Path(session_dir)
    if not base.is_dir():
        return ""

    files = sorted(
        f for f in base.iterdir()
        if f.is_file() and f.suffix.lower() in ALLOWED_EXTENSIONS
    )

    if not files:
        return ""

    parts: list[str] = []
    for f in files:
        try:
            contents = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        parts.append(f"--- {f.name} ---\n{contents}")

    return "\n\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Serve session files to stdout."
    )
    parser.add_argument("--session-dir", required=True, help="Path to the session directory")
    parser.add_argument("--query", required=True, help="Filename to read, or '*'/'all' for all files")
    args = parser.parse_args()

    if args.query in ("*", "all"):
        output = read_all_session_files(args.session_dir)
    else:
        output = read_session_file(args.session_dir, args.query)

    sys.stdout.write(output)


if __name__ == "__main__":
    main()
