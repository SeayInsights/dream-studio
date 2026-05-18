from __future__ import annotations
import json
import os
import pytest


def test_stale_session_file_deleted(spool_root):
    """Session files for dead PIDs are cleaned up."""
    from spool.ingestor import ingest_pending

    sessions_dir = spool_root / ".sessions"
    sessions_dir.mkdir()

    # Use PID 99999 which should not exist (very unlikely on any normal system)
    stale_pid = 99999
    stale_file = sessions_dir / f"{stale_pid}.json"
    stale_file.write_text(json.dumps({"pid": stale_pid}), encoding="utf-8")

    ingest_pending(root=spool_root)

    # File should be gone (if PID 99999 is not alive)
    if not _pid_alive(stale_pid):
        assert not stale_file.exists()


def test_live_session_file_preserved(spool_root):
    """Session files for live PIDs are NOT deleted."""
    from spool.ingestor import ingest_pending

    sessions_dir = spool_root / ".sessions"
    sessions_dir.mkdir()

    live_pid = os.getpid()
    live_file = sessions_dir / f"{live_pid}.json"
    live_file.write_text(json.dumps({"pid": live_pid}), encoding="utf-8")

    ingest_pending(root=spool_root)

    # Our own process's session file should still be there
    assert live_file.exists()
    live_file.unlink()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return True
