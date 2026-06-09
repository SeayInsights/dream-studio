from __future__ import annotations
import json
import os
import uuid
from pathlib import Path

from spool.config import get_spool_root
from spool.states import ensure_dirs, sessions_dir


def get_or_create_session_id(root: Path | None = None) -> str | None:
    pid = os.getpid()
    r = root if root is not None else get_spool_root()
    ensure_dirs(r)
    session_file = sessions_dir(r) / f"{pid}.json"

    if session_file.exists():
        try:
            data = json.loads(session_file.read_text(encoding="utf-8"))
            return data.get("session_id")
        except (json.JSONDecodeError, OSError):
            pass

    session_id = str(uuid.uuid4())
    try:
        session_file.write_text(
            json.dumps({"session_id": session_id, "pid": pid}),
            encoding="utf-8",
        )
        return session_id
    except OSError:
        return None
