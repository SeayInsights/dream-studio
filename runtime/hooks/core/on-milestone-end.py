#!/usr/bin/env python3
"""Hook: on-milestone-end — emit checkpoint and clear the marker at turn end.

Trigger: Stop.
Purpose: If a milestone marker exists, record completion to the milestone log,
print a checkpoint reminder, and clear the marker. If the milestone ran longer
than DIFFICULTY_THRESHOLD_MINUTES, draft a retrospective lesson for review.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _get_plugin_root() -> Path:
    sidecar = Path(__file__).resolve()
    for _ in range(8):
        candidate = sidecar / ".plugin-root"
        if candidate.is_file():
            try:
                return Path(candidate.read_text(encoding="utf-8").strip()).resolve()
            except Exception:
                pass
        sidecar = sidecar.parent
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[4]


_PLUGIN_ROOT = _get_plugin_root()
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))
if str(_PLUGIN_ROOT / "hooks") not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT / "hooks"))

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
