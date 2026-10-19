"""Stdlib-only Dream Studio home resolution, for hook code that must not import core.

runtime/lib/enforcement.py already explains why: it is copied verbatim into every
installed hook tree (see integrations/installer/claude_code_fileops.py), and importing
anything under `core` there pulls pydantic, jsonschema and the event store -- 259 ms
measured on the operator's machine, paid inside hooks that block Edit/Write/Stop.

This module exists so that constraint does not also mean duplicating the home rule by
hand. It mirrors core.config.paths.home_dir() exactly -- DREAM_STUDIO_HOME wins, then
the home a self-installed app records in its venv (APP_HOME_MARKER under sys.prefix),
else ~/.dream-studio, not created -- and MUST be kept that way:
tests/unit/test_home_means_home.py::test_runtime_lib_home_matches_core_config_paths
drives both with the same environment and asserts they agree.

Do not add anything here beyond os, sys and pathlib. The whole point of this file is that
importing it costs nothing.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

USER_DATA_DIRNAME = ".dream-studio"
APP_HOME_MARKER = "dream-studio-home"  # core.config.paths.APP_HOME_MARKER


def home_dir() -> Path:
    """DREAM_STUDIO_HOME, else the installed app's recorded home, else ~/.dream-studio."""
    override = os.environ.get("DREAM_STUDIO_HOME")
    if override:
        return Path(override).expanduser()
    marker = Path(sys.prefix) / APP_HOME_MARKER
    if marker.is_file():
        recorded = marker.read_text(encoding="utf-8").strip()
        if recorded:
            return Path(recorded)
    return Path.home() / USER_DATA_DIRNAME


def state_dir() -> Path:
    """Per-user state directory. Not created -- callers that write into it already do."""
    return home_dir() / "state"
