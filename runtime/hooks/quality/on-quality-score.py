#!/usr/bin/env python3
"""Hook: on-quality-score — advisory scoring after a milestone completes.

Trigger: Stop (ordering matters in hooks.json — run before on-milestone-end).
When a milestone marker exists, scan the git diff since the milestone
started for: test coverage proxy, debug leftovers, potential secrets,
large files, and scope. Prints a summary, appends a row to
`~/.dream-studio/meta/quality-log.md`, and writes the overall score to
`~/.dream-studio/meta/quality-score.json`. Never blocks — Director
decides.
"""

from __future__ import annotations

import sys
from pathlib import Path

from core.config import paths  # noqa: E402
from control.analysis import quality_scoring  # noqa: E402


def main() -> None:
    marker = quality_scoring.load_milestone_marker(paths.state_dir())
    if not marker:
        return

    results, score, label = quality_scoring.run_quality_checks(
        marker["started_at"], paths.project_root()
    )

    if not results:
        return

    quality_scoring.print_report(marker["command"], results, score, label)
    quality_scoring.save_outputs(marker["command"], results, score, label, paths.meta_dir())


if __name__ == "__main__":
    main()
