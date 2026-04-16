"""Cross-platform path resolution for dream-studio hooks.

All hooks call into these helpers so that user data, plugin root, and
project context resolve the same way regardless of OS, cwd, or how the
hook was invoked (shim, direct python, test harness).
"""

from __future__ import annotations

import os
from pathlib import Path

USER_DATA_DIRNAME = ".dream-studio"


def plugin_root() -> Path:
    """Return the installed plugin's root directory.

    Prefers the `CLAUDE_PLUGIN_ROOT` env var (set by Claude Code when
    invoking hooks). Falls back to walking up from this file's location
    until a `.claude-plugin/plugin.json` manifest is found — useful for
    tests and direct-script execution outside the Claude runtime.
    """
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return Path(env).resolve()

    current = Path(__file__).resolve().parent
    for candidate in [current, *current.parents]:
        if (candidate / ".claude-plugin" / "plugin.json").is_file():
            return candidate
    raise RuntimeError(
        "Could not locate plugin root. Set CLAUDE_PLUGIN_ROOT or run "
        "from inside a dream-studio checkout."
    )


def user_data_dir() -> Path:
    """Return `~/.dream-studio/`, creating it if absent."""
    path = Path.home() / USER_DATA_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def project_root() -> Path:
    """Return the project the user is currently working in."""
    return Path.cwd()


def meta_dir() -> Path:
    """Per-user meta directory for pulse/quality/token logs."""
    path = user_data_dir() / "meta"
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_dir() -> Path:
    """Per-user state directory for transient runtime state."""
    path = user_data_dir() / "state"
    path.mkdir(parents=True, exist_ok=True)
    return path


def planning_dir() -> Path:
    """Per-user planning directory for spec/plan/handoff artifacts."""
    path = user_data_dir() / "planning"
    path.mkdir(parents=True, exist_ok=True)
    return path
