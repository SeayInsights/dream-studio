"""WO-FILESDB-P3 S1+S2: `planning` category on files.db + idempotent .planning backfill.

S1 — files.db gains a 'planning' category. A files.db created under the old CHECK
(handoff/evidence/release/rollback/export) is transparently rebuilt so planning
writes succeed and existing rows/indexes survive.
S2 — every file under .planning/ (all types, INCLUDING personal) is copied into
files.db; the backfill is idempotent (unchanged files write nothing) and dry-run is
side-effect-free.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.files import store
from interfaces.cli.backfill_planning_to_filesdb import backfill_planning

_OLD_DDL = """
CREATE TABLE ds_files (
  file_id TEXT NOT NULL PRIMARY KEY, project_id TEXT,
  category TEXT NOT NULL CHECK (category IN ('handoff','evidence','release','rollback','export')),
  name TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, content_type TEXT NOT NULL,
  content BLOB NOT NULL, correlation_id TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  created_by TEXT, expires_at TEXT, checksum TEXT);
CREATE INDEX idx_ds_files_project_category ON ds_files(project_id, category);
CREATE INDEX idx_ds_files_name_version ON ds_files(name, version);
"""


# ── S1: planning category ──────────────────────────────────────────────────


def test_planning_category_is_valid():
    assert "planning" in store._VALID_CATEGORIES


def test_fresh_db_accepts_planning_write(tmp_path: Path):
    db = tmp_path / "files.db"
    fid = store.write_file("t.md", "hi", "text/markdown", "planning", db_path=db)
    assert store.read_file(fid, db_path=db)["category"] == "planning"


def test_stale_check_db_is_rebuilt_preserving_rows_and_indexes(tmp_path: Path):
    db = tmp_path / "files.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(_OLD_DDL)
    conn.execute(
        "INSERT INTO ds_files (file_id, category, name, version, content_type, content)"
        " VALUES ('legacy1','handoff','old.md',1,'text/markdown','legacy')"
    )
    conn.commit()
    conn.close()

    # write_file -> ensure_files_schema -> one-time rebuild widening the CHECK
    store.write_file("new.md", "x", "text/markdown", "planning", db_path=db)

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        legacy = conn.execute(
            "SELECT category, content FROM ds_files WHERE file_id='legacy1'"
        ).fetchone()
        table_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='ds_files'"
        ).fetchone()[0]
        idxs = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='ds_files'"
            )
            if r[0].startswith("idx_ds_files")
        }
        leftover = conn.execute(
            "SELECT name FROM sqlite_master WHERE name='_ds_files_old'"
        ).fetchone()
    finally:
        conn.close()

    assert legacy is not None and legacy["content"] == "legacy"  # row preserved
    assert "'planning'" in table_sql  # CHECK widened
    assert idxs == {"idx_ds_files_project_category", "idx_ds_files_name_version"}
    assert leftover is None  # temp table cleaned up


def test_rebuild_is_idempotent(tmp_path: Path):
    db = tmp_path / "files.db"
    store.write_file("a.md", "a", "text/markdown", "planning", db_path=db)
    # Second ensure must not rebuild again (CHECK already covers planning).
    conn = store.connect_files(db)
    try:
        store.ensure_files_schema(conn)
        assert (
            conn.execute("SELECT name FROM sqlite_master WHERE name='_ds_files_old'").fetchone()
            is None
        )
    finally:
        conn.close()


# ── S2: backfill ───────────────────────────────────────────────────────────


def _make_planning_tree(root: Path) -> None:
    (root / "specs").mkdir(parents=True)
    (root / "personal").mkdir(parents=True)
    (root / "specs" / "spec.md").write_text("# spec\n", encoding="utf-8")
    (root / "notes.yaml").write_text("k: v\n", encoding="utf-8")
    (root / "personal" / "private.md").write_text("secret\n", encoding="utf-8")
    (root / "personal" / "diagram.bin").write_bytes(b"\x00\x01\x02BIN")


def test_backfill_covers_all_files_including_personal(tmp_path: Path):
    planning = tmp_path / ".planning"
    _make_planning_tree(planning)
    db = tmp_path / "files.db"

    result = backfill_planning(planning_dir=planning, db_path=db)
    assert result["written"] == 4
    assert result["skipped"] == 0
    assert result["errors"] == []

    names = {r["name"] for r in store.list_files(category="planning", db_path=db)}
    assert names == {
        "specs/spec.md",
        "notes.yaml",
        "personal/private.md",
        "personal/diagram.bin",
    }


def test_backfill_is_idempotent(tmp_path: Path):
    planning = tmp_path / ".planning"
    _make_planning_tree(planning)
    db = tmp_path / "files.db"

    backfill_planning(planning_dir=planning, db_path=db)
    second = backfill_planning(planning_dir=planning, db_path=db)
    assert second["written"] == 0
    assert second["skipped"] == 4


def test_backfill_rewrites_only_changed_files(tmp_path: Path):
    planning = tmp_path / ".planning"
    _make_planning_tree(planning)
    db = tmp_path / "files.db"
    backfill_planning(planning_dir=planning, db_path=db)

    (planning / "specs" / "spec.md").write_text("# spec v2\n", encoding="utf-8")
    result = backfill_planning(planning_dir=planning, db_path=db)
    assert result["written"] == 1
    assert result["skipped"] == 3


def test_backfill_dry_run_writes_nothing(tmp_path: Path):
    planning = tmp_path / ".planning"
    _make_planning_tree(planning)
    db = tmp_path / "files.db"

    result = backfill_planning(planning_dir=planning, db_path=db, dry_run=True)
    assert result["written"] == 4
    assert store.list_files(category="planning", db_path=db) == []
