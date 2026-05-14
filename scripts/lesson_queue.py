"""Compatibility entrypoint for the canonical lesson queue CLI.

The implementation lives in ``interfaces/cli/lesson_queue.py``.  This file
keeps documented ``py scripts/lesson_queue.py`` invocations working without
duplicating lesson-triage logic.
"""

from __future__ import annotations

import sys

from interfaces.cli.lesson_queue import *  # noqa: F401,F403
from interfaces.cli.lesson_queue import main

if __name__ == "__main__":
    sys.exit(main())
