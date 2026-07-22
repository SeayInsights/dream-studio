"""dream-studio setup — shared bootstrap, paths, and result type.

Split from interfaces/cli/setup.py (WO-GF-CLI-split). Runs the UTF-8 console
reconfigure and REPO_ROOT/sys.path bootstrap as a module-level side effect
(preserved verbatim from the original setup.py so the facade + every sibling
module sees a UTF-8-safe stdout/stderr and a resolvable ``interfaces`` package
regardless of whether setup.py is imported or executed directly as a script).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import NamedTuple

# Force UTF-8 output on all platforms so Unicode markers render correctly.
# On Windows the default console codec is cp1252 which lacks checkmark glyphs.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
VENV_DIR = REPO_ROOT / ".venv"
REQUIREMENTS = REPO_ROOT / "requirements.txt"
HOOKS_JSON = REPO_ROOT / "hooks" / "hooks.json"


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------


class StepResult(NamedTuple):
    name: str
    passed: bool
    detail: str = ""
