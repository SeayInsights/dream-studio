"""
etl_home.py -- where the ETL scripts find the Dream Studio home, in a checkout and in an
installed plugin.

The scripts in this directory run in place: from a dream-studio checkout
(`templates/security/etl/`) and from an installed plugin (`<skill-dir>/templates/security/etl/`,
where `<skill-dir>` is the ds-security skill's own directory). A checkout has the platform's
`core` package next to them and an installed plugin does not, so the home is resolved here
and nowhere else:

  * in a checkout, `core.config.paths.home_dir()` decides, exactly as before;
  * anywhere else, DREAM_STUDIO_HOME if set, else ~/.dream-studio.

This file is a sibling of the scripts and is imported by plain name; each script puts its
own directory on sys.path first.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _checkout_root() -> Path | None:
    """The dream-studio checkout these scripts sit in, or None when they are installed."""
    root = Path(__file__).resolve().parents[3]
    return root if (root / "core" / "config" / "paths.py").is_file() else None


def home_dir() -> Path:
    """The Dream Studio home. NOT created."""
    root = _checkout_root()
    if root is not None:
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        try:
            from core.config.paths import home_dir as platform_home_dir
        except ImportError:
            pass
        else:
            return platform_home_dir()
    override = os.environ.get("DREAM_STUDIO_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".dream-studio"
