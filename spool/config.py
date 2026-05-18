from __future__ import annotations
import os
from pathlib import Path


def get_spool_root() -> Path:
    env = os.environ.get("DS_SPOOL_ROOT")
    if env:
        return Path(env).resolve()
    return Path.home() / ".dream-studio" / "events"
