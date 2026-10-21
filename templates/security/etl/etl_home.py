"""
etl_home.py -- the Dream Studio home, for the ETL scripts, with no platform import.

The scripts in this directory run in place from a dream-studio checkout
(`templates/security/etl/`) and from a skill directory the plugin or the self-install
projection wrote (`<skill-dir>/templates/security/etl/`), where there is no `core` package.
They must not import one: `core` pulls pydantic, jsonschema and the event store, and an
installed skill has none of them.

So this is the stdlib mirror of `core.config.paths.home_dir()`, in the way
`runtime/lib/home.py` is for hooks, and it is held to the same answer:

  1. DREAM_STUDIO_HOME, when set and not empty, with `~` expanded (a relative path stays
     relative, trailing separators and case are Path's, exactly as the original);
  2. else the home a self-installed app records in its venv (APP_HOME_MARKER under
     sys.prefix), when that file holds a path;
  3. else ~/.dream-studio.

NOT created. It used to delegate to `core` when it found a checkout and fall back to this
rule otherwise, which made two behaviours and left the second without the venv marker; it is
one rule now. tests/unit/test_etl_home_parity.py runs this module (standalone, `core` blocked)
and `core.config.paths.home_dir()` under the same environment matrix and requires the same
path, and tests/unit/test_home_means_home.py lists the two lines below that spell the
default, with this reason.

Do not add anything here beyond os, sys and pathlib.
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
