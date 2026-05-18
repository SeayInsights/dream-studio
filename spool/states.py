from __future__ import annotations
from enum import Enum
from pathlib import Path

from spool.config import get_spool_root


class SpoolState(Enum):
    SPOOL = "spool"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


def state_dir(state: SpoolState, root: Path | None = None) -> Path:
    r = root if root is not None else get_spool_root()
    return r / state.value


def sessions_dir(root: Path | None = None) -> Path:
    r = root if root is not None else get_spool_root()
    return r / ".sessions"


def ensure_dirs(root: Path | None = None) -> None:
    r = root if root is not None else get_spool_root()
    for state in SpoolState:
        (r / state.value).mkdir(parents=True, exist_ok=True)
    (r / ".sessions").mkdir(parents=True, exist_ok=True)
