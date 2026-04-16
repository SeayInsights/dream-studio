"""Python interpreter detection for cross-platform hook shims.

Windows ships `py` (the launcher), Linux/macOS ship `python3`, some
environments only have `python`. Try them in that order and return the
first one found on PATH.
"""

from __future__ import annotations

import shutil
import sys
from typing import Sequence

_CANDIDATES: Sequence[str] = ("py", "python3", "python")


class PythonNotFoundError(RuntimeError):
    """No Python interpreter was discoverable on PATH."""


def _install_instructions() -> str:
    if sys.platform.startswith("win"):
        return (
            "Install Python 3.10+ from https://www.python.org/downloads/ and "
            "check 'Add Python to PATH' during setup, or install via "
            "`winget install Python.Python.3.12`."
        )
    if sys.platform == "darwin":
        return (
            "Install Python 3.10+ with Homebrew (`brew install python@3.12`) "
            "or via https://www.python.org/downloads/."
        )
    return (
        "Install Python 3.10+ using your distribution's package manager — "
        "e.g. `sudo apt install python3` or `sudo dnf install python3`."
    )


def detect_python(candidates: Sequence[str] = _CANDIDATES) -> str:
    """Return the first candidate interpreter found on PATH.

    Args:
        candidates: Override the default search order in tests.

    Raises:
        PythonNotFoundError: No candidate is available. The error
            message includes OS-specific install instructions.
    """
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return found
    raise PythonNotFoundError(
        "No Python interpreter found on PATH (tried: "
        + ", ".join(candidates)
        + "). "
        + _install_instructions()
    )
