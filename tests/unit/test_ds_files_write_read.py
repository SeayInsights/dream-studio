"""WO-FILESDB-P3 S3a: `ds files write`/`read` + store.read_file_by_name.

These give the docstore a filesystem-like author/read surface addressed by logical
name, so working notes can be created and read entirely in files.db with no disk file
(the zero-disk path chosen for .planning working state).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from core.files import store
from interfaces.cli.ds_files import cmd_files_read, cmd_files_write


@pytest.fixture
def files_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "files.db"
    monkeypatch.setattr(store, "files_db_path", lambda: db)
    return db


# ── store.read_file_by_name ─────────────────────────────────────────────────


def test_read_by_name_returns_latest_version(files_db: Path):
    store.write_file("notes.md", "v1", "text/markdown", "planning")
    store.write_file("notes.md", "v2", "text/markdown", "planning")
    row = store.read_file_by_name("notes.md")
    assert row["content"] == b"v2"
    assert row["version"] == 2


def test_read_by_name_specific_version(files_db: Path):
    store.write_file("notes.md", "v1", "text/markdown", "planning")
    store.write_file("notes.md", "v2", "text/markdown", "planning")
    row = store.read_file_by_name("notes.md", version=1)
    assert row["content"] == b"v1"


def test_read_by_name_missing_raises(files_db: Path):
    with pytest.raises(KeyError):
        store.read_file_by_name("nope.md")


# ── CLI write / read ────────────────────────────────────────────────────────


def _write_args(name: str, content: str | None = None, category: str = "planning"):
    return argparse.Namespace(
        name=name,
        content=content,
        category=category,
        project_id=None,
        content_type=None,
    )


def _read_args(name: str, version: int | None = None):
    return argparse.Namespace(name=name, project_id=None, version=version)


def test_cli_write_then_read_roundtrip(files_db: Path, capsys):
    assert cmd_files_write(_write_args("personal/n.md", content="hello\nworld")) == 0
    capsys.readouterr()  # drain the write's JSON line
    assert cmd_files_read(_read_args("personal/n.md")) == 0
    assert capsys.readouterr().out == "hello\nworld"


def test_cli_write_from_stdin(files_db: Path, capsys, monkeypatch: pytest.MonkeyPatch):
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO("from stdin\n"))
    assert cmd_files_write(_write_args("s.md", content=None)) == 0
    capsys.readouterr()
    cmd_files_read(_read_args("s.md"))
    assert capsys.readouterr().out == "from stdin\n"


def test_cli_write_stores_planning_category(files_db: Path, capsys):
    cmd_files_write(_write_args("p.md", content="x", category="planning"))
    capsys.readouterr()
    assert store.read_file_by_name("p.md")["category"] == "planning"


def test_cli_read_missing_returns_error(files_db: Path, capsys):
    assert cmd_files_read(_read_args("missing.md")) == 1
    assert "No file found" in capsys.readouterr().err


def test_cli_read_reads_specific_version(files_db: Path, capsys):
    cmd_files_write(_write_args("v.md", content="one"))
    cmd_files_write(_write_args("v.md", content="two"))
    capsys.readouterr()
    cmd_files_read(_read_args("v.md", version=1))
    assert capsys.readouterr().out == "one"
