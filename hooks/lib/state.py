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


def read_config() -> Dict[str, Any]:
    """Return the user config dict, or a default stub if the file is absent."""
    path = _config_path()
    if not path.is_file():
        return {"schema_version": SCHEMA_VERSION}
    with path.open("r", encoding="utf-8") as f:
        doc = json.load(f)
    _check_schema(doc, path)
    return doc


def write_config(data: Dict[str, Any]) -> Path:
    """Persist the user config, stamping schema_version."""
    path = _config_path()
    payload = {**data, "schema_version": SCHEMA_VERSION}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    return path


def read_pulse() -> Dict[str, Any]:
    """Return the latest pulse snapshot, or an empty dict if none exists."""
    path = _pulse_path()
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as f:
        doc = json.load(f)
    _check_schema(doc, path)
    return doc


def write_pulse(data: Dict[str, Any]) -> Path:
    """Persist the latest pulse snapshot, stamping schema_version."""
    path = _pulse_path()
    payload = {**data, "schema_version": SCHEMA_VERSION}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    return path
