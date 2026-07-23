"""WO-FILESDB-P3 S3b-3: memory-ingest reads GOTCHAS.md from the docstore.

Under zero-disk .planning, GOTCHAS.md lives in files.db (category 'planning'). The
gotcha ingest pass reads it from the docstore (disk-fallback during transition) instead
of globbing .planning on disk.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.files import store
from interfaces.cli.ds_memory_ingest import _docstore_gotcha_sources, _pass1_gotchas


@pytest.fixture
def files_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "files.db"
    monkeypatch.setattr(store, "files_db_path", lambda: db)
    return db


# ── _docstore_gotcha_sources ────────────────────────────────────────────────


def test_returns_gotchas_from_docstore(files_db: Path):
    store.write_file("specs/foo/GOTCHAS.md", "## G1\nctx\n", "text/markdown", "planning")
    store.write_file("bar/GOTCHAS.md", "## G2\nctx\n", "text/markdown", "planning")
    store.write_file("specs/foo/spec.md", "not a gotcha\n", "text/markdown", "planning")

    names = {p.as_posix() for p, _ in _docstore_gotcha_sources(None)}
    assert names == {"specs/foo/GOTCHAS.md", "bar/GOTCHAS.md"}


def test_project_scoped_filter(files_db: Path):
    store.write_file("proj-a/GOTCHAS.md", "## A\nctx\n", "text/markdown", "planning")
    store.write_file("proj-b/GOTCHAS.md", "## B\nctx\n", "text/markdown", "planning")
    names = {p.as_posix() for p, _ in _docstore_gotcha_sources("proj-a")}
    assert names == {"proj-a/GOTCHAS.md"}


def test_content_is_returned(files_db: Path):
    store.write_file("x/GOTCHAS.md", "## Title\nbody\n", "text/markdown", "planning")
    sources = dict((p.as_posix(), c) for p, c in _docstore_gotcha_sources(None))
    assert sources["x/GOTCHAS.md"] == "## Title\nbody\n"


# ── end-to-end: _pass1_gotchas ingests from the docstore ────────────────────


def test_pass1_ingests_gotcha_from_docstore(files_db: Path, tmp_path: Path):
    store.write_file(
        "specs/demo/GOTCHAS.md",
        "## Docstore gotcha title\nSome context here.\nFix: do the thing.\n",
        "text/markdown",
        "planning",
    )
    studio = tmp_path / "studio.db"
    bootstrap_database(studio)
    conn = sqlite3.connect(str(studio))
    try:
        result = _pass1_gotchas(
            sessions_dir=tmp_path / "empty-sessions",  # does not exist -> no session files
            planning_dir=tmp_path / ".planning",  # does not exist -> no disk gotchas
            project=None,
            conn=conn,
            dry_run=False,
        )
        assert result["new"] >= 1
        rows = conn.execute(
            "SELECT title FROM reg_gotchas WHERE title LIKE 'Docstore gotcha%'"
        ).fetchall()
        assert rows, "docstore gotcha was not ingested into reg_gotchas"
    finally:
        conn.close()
