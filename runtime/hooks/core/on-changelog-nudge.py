#!/usr/bin/env python3
"""Hook: on-changelog-nudge — remind to update CHANGELOG.md when source files changed.

Trigger: Stop.
Checks git status: if tracked source files are modified/added but CHANGELOG.md is
not among them, prints a one-line advisory. Never blocks.
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
