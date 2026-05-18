from __future__ import annotations
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from spool.config import get_spool_root
from spool.states import SpoolState, ensure_dirs, state_dir


def write_event(envelope: dict[str, Any], root: Path | None = None) -> Path:
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
