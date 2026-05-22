"""Stable machine identifier for Dream Studio telemetry.

Generates a Dream Studio-managed UUID on first call and persists it at
~/.dream-studio/state/machine_id (env-overridable via DS_MACHINE_ID_PATH).
Cached per-process so repeated calls are free.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional

_DS_MACHINE_ID_PATH_ENV = "DS_MACHINE_ID_PATH"

_cached_machine_id: Optional[str] = None


def _machine_id_path() -> Path:
    override = os.environ.get(_DS_MACHINE_ID_PATH_ENV)
    if override:
        return Path(override)
    return Path.home() / ".dream-studio" / "state" / "machine_id"


def get_machine_id() -> str:
    """Returns a stable Dream Studio machine identifier.

    Reads from the persisted file if it exists. If not, generates a new UUID,
    persists it, and returns it. Result is cached for the lifetime of the process.
    Env-overridable via DS_MACHINE_ID_PATH for tests.
    """
    global _cached_machine_id
    if _cached_machine_id is not None:
        return _cached_machine_id

    path = _machine_id_path()
    try:
        text = path.read_text(encoding="utf-8").strip()
        if text:
            _cached_machine_id = text
            return _cached_machine_id
    except (OSError, IOError):
        pass

    # Generate, persist, return.
    new_id = str(uuid.uuid4())
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_id, encoding="utf-8")
    except (OSError, IOError):
        pass  # best-effort persistence; still return the ID this process will use

    _cached_machine_id = new_id
    return _cached_machine_id


def _reset_cache() -> None:
    """Clear the process-level cache. For testing only."""
    global _cached_machine_id
    _cached_machine_id = None
