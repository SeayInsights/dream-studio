"""Config and pulse state I/O with schema-version guards.

Configuration lives at `~/.dream-studio/config.json`.
Pulse snapshots live at `~/.dream-studio/meta/pulse-latest.json`.

Schema versioning: every persisted document carries `schema_version`.
Readers refuse to load a document whose schema is newer than the code
understands — better to fail loudly than silently misinterpret future
fields.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

from . import paths

SCHEMA_VERSION = 1
CONFIG_FILENAME = "config.json"
PULSE_FILENAME = "pulse-latest.json"


class SchemaVersionError(RuntimeError):
    """Stored document's schema_version is newer than this code supports."""


def _config_path() -> Path:
    return paths.user_data_dir() / CONFIG_FILENAME


def _pulse_path() -> Path:
    return paths.meta_dir() / PULSE_FILENAME


def _check_schema(doc: Dict[str, Any], source: Path) -> None:
    stored = doc.get("schema_version", 1)
    if not isinstance(stored, int) or stored > SCHEMA_VERSION:
        raise SchemaVersionError(
            f"{source} has schema_version={stored!r}, but this dream-studio "
            f"only understands up to {SCHEMA_VERSION}. Upgrade the plugin "
            "to read this file."
        )


def _atomic_write(path: Path, payload: Dict[str, Any]) -> None:
    """Write JSON atomically via temp file + rename to prevent partial writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_config() -> Dict[str, Any]:
    """Return the user config dict, or a default stub if the file is absent or corrupt."""
    path = _config_path()
    if not path.is_file():
        return {"schema_version": SCHEMA_VERSION}
    try:
        with path.open("r", encoding="utf-8") as f:
            doc = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"schema_version": SCHEMA_VERSION}
    _check_schema(doc, path)
    return doc


def write_config(data: Dict[str, Any]) -> Path:
    """Persist the user config atomically, stamping schema_version."""
    path = _config_path()
    _atomic_write(path, {**data, "schema_version": SCHEMA_VERSION})
    return path


def read_pulse() -> Dict[str, Any]:
    """Return the latest pulse snapshot, or an empty dict if none exists."""
    path = _pulse_path()
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            doc = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    _check_schema(doc, path)
    return doc


def write_pulse(data: Dict[str, Any]) -> Path:
    """Persist the latest pulse snapshot atomically, stamping schema_version."""
    path = _pulse_path()
    _atomic_write(path, {**data, "schema_version": SCHEMA_VERSION})
    return path


def get_quiet_mode() -> int:
    """Return the number of turns advisory hooks should remain suppressed (0 = normal)."""
    try:
        return int(read_config().get("quiet_mode", 0))
    except (TypeError, ValueError):
        return 0


def set_quiet_mode(turns: int) -> None:
    """Set how many turns advisory hooks should be suppressed.

    Hooks call this to decrement the counter each turn:
        remaining = get_quiet_mode()
        if remaining > 0:
            set_quiet_mode(remaining - 1)
            return  # suppressed this turn
    """
    cfg = read_config()
    cfg["quiet_mode"] = max(0, int(turns))
    write_config(cfg)
