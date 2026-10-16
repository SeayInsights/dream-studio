"""Shared constants and helpers for the Claude Code installer.

WO-GF-CONTROL-INSTALL-split: implementation moved to claude_code_{shared,
fileops,launcher,installer}.py; integrations/installer/claude_code.py
re-exports the public+private surface so existing
`from integrations.installer.claude_code import X` callers are unchanged.
"""

from __future__ import annotations

import hashlib
import platform
import sys
from pathlib import Path

from core.config.paths import code_root

# The code root: the checkout, or the installed app's site-packages (core.config.paths).
_INSTALLER_DIR = Path(__file__).resolve().parent
_REPO_ROOT = code_root()
_DS_ENTRY = _REPO_ROOT / "interfaces" / "cli" / "ds_entry.py"

_CHUNK_SIZE = 65536  # 64 KB — used for chunked hashing of files > 1 MB

_DS_PATH_MARKER = "# Dream Studio PATH — added by ds installer"


def _python_cmd() -> str:
    """Return the Python command for generated hook scripts (WO-INSTALL-PY-ABS).

    Uses the ABSOLUTE ``sys.executable`` — the interpreter that installed Dream Studio — on
    every platform, so a hook command is self-contained and a reinstall regenerates the same
    working command instead of clobbering an operator's manual absolute-path edit. Windows
    previously emitted the bare ``py`` launcher, which is not reliably resolvable in the hook
    exec environment (and forced operators to re-apply an absolute path after every
    ``ds integrate install``). On Windows the path is quoted and forward-slashed to match the
    ``hooks_dir`` convention and survive spaces (e.g. ``C:/Users/Example User/...``).

    From a self-installed app (``ds self-install``) this is that app's venv python, spelled
    through ``<home>/app/current`` so a later self-install or rollback, which only moves
    ``current``, switches every hook with it."""
    exe = _app_python()
    if platform.system() == "Windows":
        return f'"{exe.replace(chr(92), "/")}"'
    return exe


def _app_python() -> str:
    """The interpreter running this installer, via <home>/app/current when that is it."""
    from core.config.paths import installed_app_home

    exe = Path(sys.executable)
    home = installed_app_home()
    if home is not None:
        current_venv = home / "app" / "current" / "venv"
        try:
            if current_venv.resolve() == Path(sys.prefix).resolve():
                return str(current_venv / exe.relative_to(Path(sys.prefix)))
        except (OSError, ValueError):
            pass
    return str(exe)


def _compute_file_hash_chunked(path: Path) -> str:
    """SHA-256 of a file using chunked reads to avoid loading large files into memory."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(_CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()
