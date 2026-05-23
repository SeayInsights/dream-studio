from __future__ import annotations
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from spool.config import get_spool_root
from spool.states import SpoolState, ensure_dirs, state_dir


def _validate_payload_keys(envelope: dict[str, Any]) -> None:
    """Raise ValueError if a required payload key is absent for this event type."""
    try:
        from config.event_type_registry import get_entry

        event_type = envelope.get("event_type", "")
        entry = get_entry(event_type)
        if entry is None or not entry.payload_required_keys:
            return
        payload = envelope.get("payload") or {}
        missing = entry.payload_required_keys - payload.keys()
        if missing:
            raise ValueError(
                f"Event '{event_type}' is missing required payload keys: {sorted(missing)}"
            )
    except ValueError:
        raise
    except Exception:
        pass


def write_event(envelope: dict[str, Any], root: Path | None = None) -> Path:
    _validate_payload_keys(envelope)
    if "schema_version" not in envelope:
        envelope = {**envelope, "schema_version": 1}
    if "event_id" not in envelope:
        envelope = {**envelope, "event_id": str(uuid.uuid4())}
    r = root if root is not None else get_spool_root()
    ensure_dirs(r)
    dest_dir = state_dir(SpoolState.SPOOL, r)
    event_id = envelope.get("event_id", "unknown")
    dest = dest_dir / f"{event_id}.json"

    fd, tmp_path = tempfile.mkstemp(dir=dest_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(envelope, f, ensure_ascii=False)
        os.replace(tmp_path, dest)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return dest
