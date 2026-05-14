#!/usr/bin/env python3
"""Hook: on-changelog-nudge — remind to update CHANGELOG.md when source files changed.

Trigger: Stop.
Checks git status: if tracked source files are modified/added but CHANGELOG.md is
not among them, prints a one-line advisory. Never blocks.
"""

from __future__ import annotations

import sys
from pathlib import Path

from core.utils import changelog_helpers
from core.config import paths  # noqa: E402


def main() -> None:
    root = changelog_helpers.find_project_root(paths.project_root())
    status_lines = changelog_helpers.get_git_status(root)
    if not status_lines:
        return

    analysis = changelog_helpers.analyze_changes(status_lines)

    if analysis["source_changed"] and not analysis["changelog_changed"]:
        changelog_helpers.print_changelog_nudge()

    if analysis["readme_changed"]:
        changelog_helpers.check_and_nudge_readme_quality(root)


if __name__ == "__main__":
    main()
