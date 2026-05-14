#!/usr/bin/env python3
"""Hook: on-milestone-end — emit checkpoint and clear the marker at turn end.

Trigger: Stop.
Purpose: If a milestone marker exists, record completion to the milestone log,
print a checkpoint reminder, and clear the marker. If the milestone ran longer
than DIFFICULTY_THRESHOLD_MINUTES, draft a retrospective lesson for review.
"""

from __future__ import annotations

import sys
from pathlib import Path

from core.utils import milestone
from core.config import paths  # noqa: E402


def main() -> None:
    marker_data = milestone.load_and_clear_marker(paths.state_dir())
    if not marker_data:
        return

    milestone.log_completion(marker_data, paths.meta_dir())
    milestone.print_checkpoint(marker_data)

    try:
        milestone.draft_lesson_if_long(marker_data, paths.meta_dir())
    except Exception:
        pass


if __name__ == "__main__":
    main()
