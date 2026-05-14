"""Debug logging utilities for hooks."""

from __future__ import annotations

import os
import sys


def is_debug_enabled() -> bool:
    """Check if debug logging is enabled via environment variable."""
    return os.environ.get("DREAM_STUDIO_DEBUG", "").lower() in ("1", "true")


def debug(hook_name: str, message: str) -> None:
    """Log debug message to stderr if debug mode is enabled."""
    if is_debug_enabled():
        print(f"[{hook_name}] {message}", file=sys.stderr, flush=True)
