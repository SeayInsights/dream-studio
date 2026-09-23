"""Stdlib-only Dream Studio home resolution, for hook code that must not import core.

runtime/lib/enforcement.py already explains why: it is copied verbatim into every
installed hook tree (see integrations/installer/claude_code_fileops.py), and importing
anything under `core` there pulls pydantic, jsonschema and the event store -- 259 ms
measured on the operator's machine, paid inside hooks that block Edit/Write/Stop.

This module exists so that constraint does not also mean duplicating the home rule by
hand. It mirrors core.config.paths.home_dir() exactly -- DREAM_STUDIO_HOME wins, else
~/.dream-studio, not created -- and MUST be kept that way:
tests/unit/test_home_means_home.py::test_runtime_lib_home_matches_core_config_paths
drives both with the same environment and asserts they agree.

Do not add anything here beyond os and pathlib. The whole point of this file is that
importing it costs nothing.
"""

from __future__ import annotations

import os
from pathlib import Path

USER_DATA_DIRNAME = ".dream-studio"


def home_dir() -> Path:
    """The Dream Studio home -- DREAM_STUDIO_HOME, else ~/.dream-studio -- NOT created."""
    override = os.environ.get("DREAM_STUDIO_HOME")
    return Path(override).expanduser() if override else Path.home() / USER_DATA_DIRNAME


def state_dir() -> Path:
    """Per-user state directory. Not created -- callers that write into it already do."""
    return home_dir() / "state"
