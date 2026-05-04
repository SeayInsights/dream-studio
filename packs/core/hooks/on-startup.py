#!/usr/bin/env python3
"""Startup hook - runs when dream-studio initializes.

Triggers the repo update checker in the background without blocking
the main session execution.
"""

import subprocess
from pathlib import Path


def main() -> None:
    """Run repo update checker in background."""
    try:
        subprocess.Popen(
            ["py", "scripts/check_repo_updates.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=Path(__file__).parent.parent.parent,
        )
    except Exception:
        # Log but don't fail startup if checker fails
        pass


if __name__ == "__main__":
    main()
