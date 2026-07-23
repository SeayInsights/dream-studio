"""WO-FILESDB-P3 S3b-1: ds_files.work_order_id soft reference.

A queryable logical link from a docstore artifact to a work order — "which docs
track to this work order" = list_files(work_order_id=...). NOT an enforced FK
(files.db and studio.db are separate SQLite files); the relationship's truth stays
in the authority. Content stays in files.db.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pytest

from core.files import store
from interfaces.cli.ds_files import cmd_files_list, cmd_files_write

# Schema as of S1/S3a: 'planning' in the CHECK, but NO work_order_id column yet.
_S1_ERA_DDL = """
CREATE TABLE ds_files (
  file_id TEXT NOT NULL PRIMARY KEY, project_id TEXT,
  category TEXT NOT NULL CHECK (category IN ('handoff','evidence','release','rollback','export','planning')),
  name TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, content_type TEXT NOT NULL,
  content BLOB NOT NULL, correlation_id TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  created_by TEXT, expires_at TEXT, checksum TEXT);
"""

# Ancient schema: OLD category CHECK (no 'planning') AND no work_order_id column.
_ANCIENT_DDL = """
CREATE TABLE ds_files (
  file_id TEXT NOT NULL PRIMARY KEY, project_id TEXT,
  category TEXT NOT NULL CHECK (category IN ('handoff','evidence','release','rollback','export')),
  name TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, content_type TEXT NOT NULL,
  content BLOB NOT NULL, correlation_id TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  created_by TEXT, expires_at TEXT, checksum TEXT);
"""


def _seed(db: Path, ddl: str) -> None:
    conn = sqlite3.connect(str(db))
    conn.executescript(ddl)
    conn.execute(
        "INSERT INTO ds_files (file_id, category, name, version, content_type, content)"
        " VALUES ('legacy1','handoff','old.md',1,'text/markdown','legacy')"
    )
    conn.commit()
    conn.close()


# ── store: write + query by work_order_id ───────────────────────────────────


def test_write_stores_work_order_id(tmp_path: Path):
    db = tmp_path / "files.db"
    store.write_file("a.md", "x", "text/markdown", "planning", work_order_id="wo-A", db_path=db)
    rows = store.list_files(work_order_id="wo-A", db_path=db)
    assert len(rows) == 1 and rows[0]["work_order_id"] == "wo-A"


def test_list_by_work_order_filters(tmp_path: Path):
    db = tmp_path / "files.db"
    store.write_file("a.md", "x", "text/markdown", "planning", work_order_id="wo-A", db_path=db)
    store.write_file("b.md", "y", "text/markdown", "planning", work_order_id="wo-A", db_path=db)
    store.write_file("c.md", "z", "text/markdown", "planning", work_order_id="wo-B", db_path=db)
    store.write_file("d.md", "w", "text/markdown", "planning", db_path=db)  # unlinked
    assert {r["name"] for r in store.list_files(work_order_id="wo-A", db_path=db)} == {
        "a.md",
        "b.md",
    }
    assert {r["name"] for r in store.list_files(work_order_id="wo-B", db_path=db)} == {"c.md"}


def test_unlinked_write_has_null_work_order(tmp_path: Path):
    db = tmp_path / "files.db"
    store.write_file("n.md", "x", "text/markdown", "planning", db_path=db)
    assert store.read_file_by_name("n.md", db_path=db)["work_order_id"] is None


# ── migration: add column to existing DBs ───────────────────────────────────


def test_s1_era_db_gains_work_order_id_column(tmp_path: Path):
    db = tmp_path / "files.db"
    _seed(db, _S1_ERA_DDL)  # planning CHECK present, no work_order_id column
    store.write_file("new.md", "x", "text/markdown", "planning", work_order_id="wo-Z", db_path=db)
    # legacy row preserved (work_order_id NULL), new row linked
    assert store.read_file_by_name("old.md", db_path=db)["work_order_id"] is None
    assert store.list_files(work_order_id="wo-Z", db_path=db)[0]["name"] == "new.md"


def test_ancient_db_migrates_check_and_column_together(tmp_path: Path):
    db = tmp_path / "files.db"
    _seed(db, _ANCIENT_DDL)  # old CHECK (no planning) AND no work_order_id
    # This requires BOTH: add work_order_id column + widen the CHECK for 'planning'.
    store.write_file("p.md", "x", "text/markdown", "planning", work_order_id="wo-Q", db_path=db)

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(ds_files)")}
        table_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='ds_files'"
        ).fetchone()[0]
        legacy = conn.execute("SELECT content FROM ds_files WHERE file_id='legacy1'").fetchone()
    finally:
        conn.close()

    assert "work_order_id" in cols  # column added
    assert "'planning'" in table_sql  # CHECK widened
    assert legacy is not None and legacy["content"] == "legacy"  # data preserved
    assert store.list_files(work_order_id="wo-Q", db_path=db)[0]["name"] == "p.md"


def test_rebuild_preserves_existing_work_order_id(tmp_path: Path):
    """A DB that already has work_order_id but an outdated CHECK must not lose the
    work_order_id data when the CHECK-widening rebuild runs (dynamic column copy)."""
    db = tmp_path / "files.db"
    conn = sqlite3.connect(str(db))
    # work_order_id present, but CHECK missing 'planning' -> forces a rebuild on ensure.
    conn.executescript("""
        CREATE TABLE ds_files (
          file_id TEXT NOT NULL PRIMARY KEY, project_id TEXT, work_order_id TEXT,
          category TEXT NOT NULL CHECK (category IN ('handoff','evidence','release','rollback','export')),
          name TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, content_type TEXT NOT NULL,
          content BLOB NOT NULL, correlation_id TEXT,
          created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
          created_by TEXT, expires_at TEXT, checksum TEXT);
        INSERT INTO ds_files (file_id, work_order_id, category, name, version, content_type, content)
          VALUES ('keep1','wo-KEEP','handoff','k.md',1,'text/markdown','k');
        """)
    conn.commit()
    conn.close()

    store.write_file("p.md", "x", "text/markdown", "planning", db_path=db)  # triggers rebuild
    # the pre-existing work_order_id survived the rebuild
    assert store.list_files(work_order_id="wo-KEEP", db_path=db)[0]["name"] == "k.md"


# ── CLI ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def files_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "files.db"
    monkeypatch.setattr(store, "files_db_path", lambda: db)
    return db


def test_cli_write_with_work_order_then_list(files_db: Path, capsys):
    args = argparse.Namespace(
        name="wo-note.md",
        content="hi",
        category="planning",
        project_id=None,
        content_type=None,
        work_order_id="wo-123",
    )
    assert cmd_files_write(args) == 0
    capsys.readouterr()
    list_args = argparse.Namespace(project_id=None, category="planning", work_order_id="wo-123")
    assert cmd_files_list(list_args) == 0
    out = capsys.readouterr().out
    assert "wo-note.md" in out and "1 file(s)." in out
