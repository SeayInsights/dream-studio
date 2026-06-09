"""Tests for core/files/store.py (WO-TS5 — files.db artifact store)."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402

from core.files.store import (  # noqa: E402
    connect_files,
    ensure_files_schema,
    list_files,
    read_file,
    write_file,
)


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    return tmp_path / "files.db"


class TestWriteFile:
    def test_returns_file_id(self, db):
        fid = write_file("test.txt", b"hello", "text/plain", "handoff", db_path=db)
        assert isinstance(fid, str) and len(fid) == 36

    def test_read_returns_correct_fields(self, db):
        fid = write_file(
            "report.md",
            b"# Report",
            "text/markdown",
            "evidence",
            project_id="proj-1",
            db_path=db,
        )
        row = read_file(fid, db_path=db)
        assert row["file_id"] == fid
        assert row["name"] == "report.md"
        assert row["category"] == "evidence"
        assert row["project_id"] == "proj-1"
        assert row["content"] == b"# Report"
        assert row["version"] == 1

    def test_checksum_is_sha256_hex(self, db):
        content = b"artifact content"
        fid = write_file("a.bin", content, "application/octet-stream", "release", db_path=db)
        row = read_file(fid, db_path=db)
        expected = hashlib.sha256(content).hexdigest()
        assert row["checksum"] == expected

    def test_str_content_stored_as_bytes(self, db):
        fid = write_file("notes.txt", "hello world", "text/plain", "export", db_path=db)
        row = read_file(fid, db_path=db)
        assert row["content"] == b"hello world"

    def test_version_increments_per_name_and_project(self, db):
        write_file("handoff.md", b"v1", "text/markdown", "handoff", project_id="p1", db_path=db)
        write_file("handoff.md", b"v2", "text/markdown", "handoff", project_id="p1", db_path=db)
        fid3 = write_file(
            "handoff.md", b"v3", "text/markdown", "handoff", project_id="p1", db_path=db
        )
        row = read_file(fid3, db_path=db)
        assert row["version"] == 3

    def test_different_project_resets_version(self, db):
        write_file("f.md", b"x", "text/plain", "handoff", project_id="p1", db_path=db)
        fid = write_file("f.md", b"x", "text/plain", "handoff", project_id="p2", db_path=db)
        row = read_file(fid, db_path=db)
        assert row["version"] == 1

    def test_invalid_category_raises(self, db):
        with pytest.raises(ValueError, match="Invalid category"):
            write_file("x.txt", b"x", "text/plain", "bogus", db_path=db)


class TestReadFile:
    def test_raises_key_error_for_missing_id(self, db):
        conn = connect_files(db)
        ensure_files_schema(conn)
        conn.close()
        with pytest.raises(KeyError):
            read_file("nonexistent-id", db_path=db)


class TestListFiles:
    def test_list_returns_all_without_filter(self, db):
        write_file("a.md", b"1", "text/plain", "handoff", project_id="p1", db_path=db)
        write_file("b.md", b"2", "text/plain", "evidence", project_id="p2", db_path=db)
        rows = list_files(db_path=db)
        assert len(rows) == 2

    def test_filter_by_project_id(self, db):
        write_file("a.md", b"1", "text/plain", "handoff", project_id="p1", db_path=db)
        write_file("b.md", b"2", "text/plain", "handoff", project_id="p2", db_path=db)
        rows = list_files(project_id="p1", db_path=db)
        assert len(rows) == 1
        assert rows[0]["project_id"] == "p1"

    def test_filter_by_category(self, db):
        write_file("a.md", b"1", "text/plain", "handoff", db_path=db)
        write_file("b.md", b"2", "text/plain", "evidence", db_path=db)
        rows = list_files(category="handoff", db_path=db)
        assert len(rows) == 1
        assert rows[0]["category"] == "handoff"

    def test_list_excludes_content_blob(self, db):
        write_file("a.md", b"blob content", "text/plain", "export", db_path=db)
        rows = list_files(db_path=db)
        assert "content" not in rows[0]

    def test_invalid_category_raises(self, db):
        with pytest.raises(ValueError, match="Invalid category"):
            list_files(category="unknown", db_path=db)


class TestEnsureFilesSchema:
    def test_idempotent(self, db):
        conn = connect_files(db)
        ensure_files_schema(conn)
        ensure_files_schema(conn)
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ds_files'"
        ).fetchall()
        conn.close()
        assert len(rows) == 1
