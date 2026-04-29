"""Unit tests for hooks.lib.memory_search."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))

from lib.memory_search import MemorySearch  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mem_dir(tmp_path: Path) -> Path:
    """A fresh temporary memory directory with a few seed files."""
    (tmp_path / "power-bi.md").write_text(
        "# Power BI\n\nDAX measures, calculated columns, Power Query M.",
        encoding="utf-8",
    )
    (tmp_path / "godot.md").write_text(
        "# Godot\n\nGDScript, scenes, signals, 2D physics.",
        encoding="utf-8",
    )
    (tmp_path / "career.md").write_text(
        "# Career\n\nJob search, offer evaluation, salary negotiation.",
        encoding="utf-8",
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Schema / DB creation
# ---------------------------------------------------------------------------


def test_build_index_creates_db(mem_dir: Path) -> None:
    ms = MemorySearch(mem_dir)
    ms.build_index()
    assert (mem_dir / "memory.db").exists()
    ms.close()


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def test_search_returns_relevant_results(mem_dir: Path) -> None:
    ms = MemorySearch(mem_dir)
    ms.build_index()
    results = ms.search("Power BI DAX")
    assert len(results) >= 1
    top = results[0]
    assert "power-bi" in top["path"]
    assert isinstance(top["score"], float)
    assert isinstance(top["snippet"], str)
    ms.close()


def test_search_respects_top_k(mem_dir: Path) -> None:
    ms = MemorySearch(mem_dir)
    ms.build_index()
    results = ms.search("the", top_k=1)
    assert len(results) <= 1
    ms.close()


def test_search_unrelated_query_returns_empty(mem_dir: Path) -> None:
    ms = MemorySearch(mem_dir)
    ms.build_index()
    results = ms.search("xyzzy frobnicator")
    assert results == []
    ms.close()


def test_search_empty_query_returns_empty(mem_dir: Path) -> None:
    ms = MemorySearch(mem_dir)
    ms.build_index()
    assert ms.search("") == []
    ms.close()


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------


def test_refresh_if_stale_skips_unchanged(mem_dir: Path, tmp_path: Path) -> None:
    ms = MemorySearch(mem_dir)
    ms.build_index()

    # Record mtime stored after initial build
    import sqlite3
    conn = sqlite3.connect(str(mem_dir / "memory.db"))
    rows_before = {r[0]: r[1] for r in conn.execute("SELECT path, mtime FROM memory_meta")}
    conn.close()

    # Refresh without touching files — nothing should change
    ms.refresh_if_stale()

    conn = sqlite3.connect(str(mem_dir / "memory.db"))
    rows_after = {r[0]: r[1] for r in conn.execute("SELECT path, mtime FROM memory_meta")}
    conn.close()

    assert rows_before == rows_after
    ms.close()


def test_refresh_if_stale_reindexes_modified_file(mem_dir: Path) -> None:
    ms = MemorySearch(mem_dir)
    ms.build_index()

    # Modify one file
    power_bi = mem_dir / "power-bi.md"
    time.sleep(0.02)  # ensure mtime changes
    power_bi.write_text("# Power BI updated\n\nNew content added.", encoding="utf-8")

    ms.refresh_if_stale()
    results = ms.search("New content added")
    assert any("power-bi" in r["path"] for r in results)
    ms.close()


def test_refresh_removes_deleted_files(mem_dir: Path) -> None:
    ms = MemorySearch(mem_dir)
    ms.build_index()

    (mem_dir / "career.md").unlink()
    ms.refresh_if_stale()

    results = ms.search("salary negotiation")
    assert results == []
    ms.close()


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------


def test_archive_stale_moves_files(mem_dir: Path) -> None:
    ms = MemorySearch(mem_dir)
    ms.build_index()

    # Manually set last_accessed to old timestamp
    import sqlite3
    old_ts = time.time() - (100 * 86400)  # 100 days ago
    conn = sqlite3.connect(str(mem_dir / "memory.db"))
    conn.execute("UPDATE memory_meta SET last_accessed = ?", (old_ts,))
    conn.commit()
    conn.close()

    count = ms.archive_stale(days=90)
    assert count == 3  # all three files moved
    assert (mem_dir / "archive").exists()
    archived = list((mem_dir / "archive").iterdir())
    assert len(archived) == 3
    ms.close()


def test_archive_stale_skips_never_accessed(mem_dir: Path) -> None:
    """Files with last_accessed == 0 (never searched) should NOT be archived."""
    ms = MemorySearch(mem_dir)
    ms.build_index()
    # last_accessed defaults to 0 — never accessed, so should not be archived
    count = ms.archive_stale(days=90)
    assert count == 0
    ms.close()


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------


def test_rebuild_500_entries_completes(tmp_path: Path) -> None:
    # Verifies build_index is not quadratic — disk I/O dominates on Windows
    # so we just assert it finishes in a reasonable wall-clock budget (10s).
    for i in range(500):
        (tmp_path / f"entry-{i:04d}.md").write_text(
            f"# Entry {i}\n\nSynthetic content for benchmark entry number {i}.",
            encoding="utf-8",
        )
    ms = MemorySearch(tmp_path)
    start = time.perf_counter()
    ms.build_index()
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 10_000, f"build_index took {elapsed_ms:.1f}ms (limit 10 000ms)"
    ms.close()


# ---------------------------------------------------------------------------
# prune_memory_md
# ---------------------------------------------------------------------------


def test_prune_memory_md_removes_archived_entries(mem_dir: Path) -> None:
    ms = MemorySearch(mem_dir)
    ms.build_index()

    memory_md = mem_dir / "MEMORY.md"
    memory_md.write_text(
        "- [Power BI](power-bi.md) — BI notes\n"
        "- [Godot](godot.md) — game notes\n"
        "- [Career](career.md) — career notes\n",
        encoding="utf-8",
    )

    # Simulate archiving power-bi.md
    archive_dir = mem_dir / "archive"
    archive_dir.mkdir()
    archived = archive_dir / "power-bi.md"
    archived.write_text("archived", encoding="utf-8")

    removed = ms.prune_memory_md([archived])
    assert removed == 1

    remaining = memory_md.read_text(encoding="utf-8")
    assert "power-bi.md" not in remaining
    assert "godot.md" in remaining
    assert "career.md" in remaining
    ms.close()


def test_prune_memory_md_tolerates_missing_file(mem_dir: Path) -> None:
    ms = MemorySearch(mem_dir)
    # No MEMORY.md in mem_dir — should return 0 without raising
    fake_archived = mem_dir / "archive" / "nonexistent.md"
    result = ms.prune_memory_md([fake_archived])
    assert result == 0
    ms.close()


# ---------------------------------------------------------------------------
# enforce_limit
# ---------------------------------------------------------------------------


def test_enforce_limit_archives_oldest_first(mem_dir: Path) -> None:
    ms = MemorySearch(mem_dir)
    ms.build_index()

    # Two additional files so we have 5 total
    (mem_dir / "extra1.md").write_text("# Extra 1\n\nContent.", encoding="utf-8")
    (mem_dir / "extra2.md").write_text("# Extra 2\n\nContent.", encoding="utf-8")
    ms.build_index()

    # Set last_accessed for all 5 files with distinct timestamps
    import sqlite3 as _sqlite3

    conn = _sqlite3.connect(str(mem_dir / "memory.db"))
    base_ts = time.time() - (200 * 86400)
    for i, row in enumerate(conn.execute("SELECT path FROM memory_meta")):
        conn.execute(
            "UPDATE memory_meta SET last_accessed = ? WHERE path = ?",
            (base_ts + i * 1000, row[0]),
        )
    conn.commit()
    conn.close()

    # Enforce limit of 3 — should archive the 2 oldest
    archived = ms.enforce_limit(max_active=3)
    assert archived == 2

    active = list(ms._iter_md_files())
    assert len(active) == 3
    ms.close()


def test_enforce_limit_skips_never_accessed(mem_dir: Path) -> None:
    ms = MemorySearch(mem_dir)
    ms.build_index()
    # All files have last_accessed == 0 (default) — none should be archived
    archived = ms.enforce_limit(max_active=0)
    assert archived == 0
    ms.close()
