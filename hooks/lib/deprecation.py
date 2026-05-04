"""Deprecation warnings for file-based document access.

Usage:
    from lib.deprecation import warn_file_read

    warn_file_read("skills/core/modes/build/SKILL.md")
"""

from __future__ import annotations

import sys
from pathlib import Path


def warn_file_read(file_path: str | Path, alternative: str | None = None) -> None:
    """Log a deprecation warning when files are read from filesystem instead of SQLite.

    Args:
        file_path: Path to the file being read from filesystem
        alternative: Optional message describing the SQLite alternative
    """
    msg_parts = [
        "\n[dream-studio DEPRECATED]",
        f"Reading '{file_path}' from filesystem.",
        "Use SQLite document store instead.",
    ]

    if alternative:
        msg_parts.append(f"Alternative: {alternative}")

    msg_parts.append("")  # trailing newline

    print("\n".join(msg_parts), file=sys.stderr, flush=True)
