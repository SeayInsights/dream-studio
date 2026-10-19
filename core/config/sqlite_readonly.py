"""A read-only SQLite open that leaves nothing behind.

`sqlite3.connect("file:...?mode=ro", uri=True)` on a WAL-mode database creates its
`-wal` and `-shm` files, and a read-only connection cannot remove them when it closes.
So a "read-only" `ds doctor` or `self-install --dry-run` against a cleanly closed
authority left two new files in the operator's state directory.

When the database has no WAL content to read (no `-wal` file, or an empty one), every
committed page is in the main file and `immutable=1` reads it without creating or
locking anything. When a `-wal` with content exists, another process has the
database open and the sidecars are already there; a plain `mode=ro` open then reads
the WAL as well. An immutable read is a snapshot: a write landing while it runs may
not be seen, which suits a report that is read once.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def connect_read_only(db_path: str | Path, *, timeout: float = 30.0) -> sqlite3.Connection:
    """Open *db_path* (which must exist) read-only, creating no file beside it."""
    db_path = Path(db_path)
    wal = Path(f"{db_path}-wal")
    has_wal_content = wal.is_file() and wal.stat().st_size > 0
    flags = "mode=ro" if has_wal_content else "mode=ro&immutable=1"
    return sqlite3.connect(f"{db_path.resolve().as_uri()}?{flags}", uri=True, timeout=timeout)
