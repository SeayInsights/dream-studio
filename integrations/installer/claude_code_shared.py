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

# Repo root: integrations/installer/claude_code.py → integrations/installer → integrations → repo
_INSTALLER_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _INSTALLER_DIR.parent.parent
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
    ``hooks_dir`` convention and survive spaces (e.g. ``C:/Users/Example User/...``)."""
    if platform.system() == "Windows":
        return f'"{sys.executable.replace(chr(92), "/")}"'
    return sys.executable


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
