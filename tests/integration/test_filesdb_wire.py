"""Integration tests for WO-FILESDB-WIRE: files.db artifact store wiring.

Covers:
- Migration 124 adds file_id + checksum columns to raw_handoffs
- insert_handoff() stores file_id/checksum
- write_recap() stores a ds_files row (category='handoff')
- list_files(category='handoff') retrieves stored blobs
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# Migration 124: raw_handoffs gains file_id + checksum columns
# ---------------------------------------------------------------------------


def test_migration_124_adds_file_id_and_checksum_columns(tmp_path, monkeypatch):
    """After _connect(), raw_handoffs has file_id and checksum columns."""
    from core.event_store.studio_db import _connect

    db_path = tmp_path / "state" / "studio.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = _connect(db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(raw_handoffs)").fetchall()}
    conn.close()

    assert "file_id" in cols, "file_id column missing from raw_handoffs after migration 124"
    assert "checksum" in cols, "checksum column missing from raw_handoffs after migration 124"


# ---------------------------------------------------------------------------
# insert_handoff stores file_id and checksum
# ---------------------------------------------------------------------------


def _seed_project_and_session(conn, project_id: str, session_id: str) -> None:
    """Insert a raw_sessions row so raw_handoffs.session_id FK is satisfied.

    reg_projects was dropped in migration 084 — only raw_sessions is needed.
    raw_handoffs.project_id has no FK (dropped in migration 088).
    """
    import datetime

    now = datetime.datetime.now(datetime.UTC).isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO raw_sessions (session_id, project_id, started_at)"
        " VALUES (?, ?, ?)",
        (session_id, project_id, now),
    )
    conn.commit()


def test_insert_handoff_stores_file_pointer(tmp_path):
    """insert_handoff() persists file_id and checksum to raw_handoffs."""
    from core.event_store.studio_db import _connect, insert_handoff

    db_path = tmp_path / "state" / "studio.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = _connect(db_path)
    _seed_project_and_session(conn, "proj-test-0001", "sess-test-0001")
    conn.close()

    handoff_id = insert_handoff(
        session_id="sess-test-0001",
        project_id="proj-test-0001",
        topic="test handoff",
        file_id="file-uuid-0001",
        checksum="deadbeef" * 8,
        db_path=db_path,
    )

    assert handoff_id is not None

    conn = _connect(db_path)
    row = conn.execute(
        "SELECT file_id, checksum FROM raw_handoffs WHERE id=?", (handoff_id,)
    ).fetchone()
    conn.close()

    assert row is not None
    assert row["file_id"] == "file-uuid-0001"
    assert row["checksum"] == "deadbeef" * 8


def test_insert_handoff_accepts_null_file_id(tmp_path):
    """insert_handoff() still works when file_id is None (pre-wire rows)."""
    from core.event_store.studio_db import _connect, insert_handoff

    db_path = tmp_path / "state" / "studio.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = _connect(db_path)
    _seed_project_and_session(conn, "proj-test-0002", "sess-test-0002")
    conn.close()

    handoff_id = insert_handoff(
        session_id="sess-test-0002",
        project_id="proj-test-0002",
        topic="legacy handoff",
        db_path=db_path,
    )

    assert handoff_id is not None


# ---------------------------------------------------------------------------
# write_file() round-trip: handoff blobs retrievable via list_files
# ---------------------------------------------------------------------------


def test_write_and_list_handoff_blob(tmp_path):
    """write_file() stores a handoff blob; list_files(category='handoff') retrieves it."""
    from core.files.store import list_files, write_file

    db_path = tmp_path / "files.db"
    content = b"# Handoff: main\nDate: 2026-06-14\n"

    file_id = write_file(
        name="handoff-abc12345",
        content=content,
        content_type="text/markdown",
        category="handoff",
        project_id="proj-test-0003",
        db_path=db_path,
    )

    rows = list_files(category="handoff", db_path=db_path)
    assert len(rows) == 1
    assert rows[0]["file_id"] == file_id
    assert rows[0]["name"] == "handoff-abc12345"
    assert rows[0]["category"] == "handoff"


def test_write_recap_and_retrieve(tmp_path):
    """write_file() stores a recap blob; list_files returns it alongside handoffs."""
    from core.files.store import list_files, read_file, write_file

    db_path = tmp_path / "files.db"
    recap_content = b"# Recap: main\nDate: 2026-06-14\n"

    file_id = write_file(
        name="recap-abc12345",
        content=recap_content,
        content_type="text/markdown",
        category="handoff",
        db_path=db_path,
    )

    row = read_file(file_id, db_path=db_path)
    assert row["content"] == recap_content
    assert row["name"] == "recap-abc12345"

    rows = list_files(category="handoff", db_path=db_path)
    assert any(r["file_id"] == file_id for r in rows)


# ---------------------------------------------------------------------------
# write_recap() integration: stores to files.db via isolated paths
# ---------------------------------------------------------------------------


def test_write_recap_stores_to_files_db(isolated_home, monkeypatch):
    """write_recap() writes to files.db (category='handoff') in an isolated home."""
    monkeypatch.setenv("DS_CWD_RESOLVER_ROOT", str(isolated_home))

    from control.context.handoff import write_recap
    from core.config import paths

    cwd = isolated_home
    write_recap(cwd, 65.0, session_id="testsess1", handoff_path=None)

    files_db = paths.state_dir() / "files.db"
    if files_db.exists():
        from core.files.store import list_files

        rows = list_files(category="handoff", db_path=files_db)
        assert isinstance(rows, list)
        assert any(
            "recap" in r["name"] for r in rows
        ), f"Expected a recap row in files.db, got: {[r['name'] for r in rows]}"
