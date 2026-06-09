#!/usr/bin/env python3
"""Hook: on-agent-correction — log director corrections and accumulate patterns.

Trigger: PostToolUse on Edit|Write.
When the director-corrections.md file is updated, parse the newest correction,
append to corrections.log, and draft lessons when patterns repeat 3+ times.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from core.config import paths  # noqa: E402
from core.learning import correction_patterns  # noqa: E402


def main() -> None:
    file_path = os.environ.get("CLAUDE_FILE_PATH", "").strip()
    if not file_path or not correction_patterns.is_corrections_file(file_path):
        return

    correction = correction_patterns.extract_latest_correction(Path(file_path))
    if not correction:
        return

    correction_patterns.print_logged_message(correction)
    correction_patterns.log_correction(correction, paths.meta_dir())
    correction_patterns.check_and_draft_lesson(correction, paths.meta_dir())


if __name__ == "__main__":
    main()
