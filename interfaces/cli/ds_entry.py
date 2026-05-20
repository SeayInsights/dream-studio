#!/usr/bin/env python3
"""
Global entry point for the ds CLI.

Resolves the dream-studio-clean repo root from the script location and
delegates to interfaces.cli.ds. Enables running `ds` from any directory
after adding ~/.dream-studio/bin to PATH.
"""

from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info < (3, 12):
    import json as _json

    print(
        _json.dumps(
            {
                "ok": False,
                "error": "Python 3.12+ required",
                "installed": f"{sys.version_info.major}.{sys.version_info.minor}",
                "fix": "Install Python 3.12+ from python.org or run install.sh/install.ps1",
            }
        )
    )
    sys.exit(1)


def main() -> None:
    # interfaces/cli/ds_entry.py → interfaces/cli → interfaces → repo root
    here = Path(__file__).resolve().parent
    repo_root = here.parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from interfaces.cli.ds import main as ds_main

    raise SystemExit(ds_main())


if __name__ == "__main__":
    main()
