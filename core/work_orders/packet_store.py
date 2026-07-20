"""Authority-free artifact store for the file-backed WO packet system (WO-FILESDB-C3).

The file-backed WO packet system (create/render/report via ``ds_work_order.py``) is
deliberately authority-free — its artifacts are portable executor-handoff data, NOT
Dream Studio authority state, and its work-order IDs are a separate id space. This
store keeps those artifacts in a self-managed SQLite DB (``packets.db``) co-located
with the packet storage root, replacing the loose ``evals/<eval_type>.json`` (and,
in later slices, the rendered packets / results / reports / decisions) files.

It NEVER touches the Dream Studio authority (``studio.db``). The table is created on
demand, so there is no released/unreleased-migration gating and no disk fallback:
writes go straight into the table (content in a table, not loose files on disk).
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .storage import default_storage_root

_TABLE = "packet_artifacts"
_CREATE = (
    f"CREATE TABLE IF NOT EXISTS {_TABLE} ("
    " work_order_id TEXT NOT NULL,"
    " kind TEXT NOT NULL,"
    " instance_key TEXT NOT NULL DEFAULT '',"
    " content TEXT NOT NULL,"
    " created_at TEXT NOT NULL,"
    " updated_at TEXT NOT NULL,"
    " PRIMARY KEY (work_order_id, kind, instance_key))"
)


def _packet_db(storage_root: Path | str | None = None) -> Path:
    root = Path(storage_root) if storage_root is not None else default_storage_root()
    return root / "packets.db"


def _connect(storage_root: Path | str | None) -> sqlite3.Connection:
    db = _packet_db(storage_root)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.execute(_CREATE)
    return conn


def set_packet_artifact(
    work_order_id: str,
    kind: str,
    content: str,
    *,
    instance_key: str = "",
    storage_root: Path | str | None = None,
) -> bool:
    """Upsert a packet artifact into the packet store. Returns True on success.

    Multi-instance artifacts (e.g. the ~15 eval stages) pass ``instance_key`` (the
    eval_type) so each coexists per work order.
    """
    now = datetime.now(UTC).isoformat()
    conn = _connect(storage_root)
    try:
        conn.execute(
            f"INSERT INTO {_TABLE}"
            " (work_order_id, kind, instance_key, content, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(work_order_id, kind, instance_key) DO UPDATE SET"
            " content=excluded.content, updated_at=excluded.updated_at",
            (work_order_id, kind, instance_key, content, now, now),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def get_packet_artifact(
    work_order_id: str,
    kind: str,
    *,
    instance_key: str = "",
    storage_root: Path | str | None = None,
) -> str | None:
    """Return a stored packet artifact's content, or None if absent."""
    conn = _connect(storage_root)
    try:
        row = conn.execute(
            f"SELECT content FROM {_TABLE} WHERE work_order_id=? AND kind=? AND instance_key=?",
            (work_order_id, kind, instance_key),
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def list_packet_artifacts(
    work_order_id: str,
    kind: str,
    *,
    storage_root: Path | str | None = None,
) -> list[tuple[str, str]]:
    """Return ``[(instance_key, content), ...]`` for all rows of a kind, ordered."""
    conn = _connect(storage_root)
    try:
        rows = conn.execute(
            f"SELECT instance_key, content FROM {_TABLE}"
            " WHERE work_order_id=? AND kind=? ORDER BY instance_key",
            (work_order_id, kind),
        ).fetchall()
        return [(r[0], r[1]) for r in rows]
    finally:
        conn.close()
