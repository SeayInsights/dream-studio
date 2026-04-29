"""SQLite FTS5-based semantic memory search for dream-studio.

Indexes all .md files in a memory directory and supports BM25-ranked
full-text search, incremental refresh, and stale-file archiving.
"""

from __future__ import annotations

import shutil
import sqlite3
import time
from pathlib import Path
from typing import TypedDict


class SearchResult(TypedDict):
    path: str
    score: float
    snippet: str


class MemorySearch:
    """Full-text index over a directory of markdown memory files."""

    def __init__(self, memory_dir: Path) -> None:
        self.memory_dir = Path(memory_dir)
        self.db_path = self.memory_dir / "memory.db"
        self._fts5_ok = False
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Connection / init
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self.memory_dir.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._ensure_schema()
        return self._conn

    def _ensure_schema(self) -> None:
        conn = self._conn
        assert conn is not None

        # FTS5 availability guard
        try:
            conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_probe USING fts5(x)")
            conn.execute("DROP TABLE IF EXISTS _fts5_probe")
            self._fts5_ok = True
        except sqlite3.OperationalError:
            self._fts5_ok = False
            return

        conn.executescript(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                path UNINDEXED,
                content,
                tokenize = 'porter ascii'
            );

            CREATE TABLE IF NOT EXISTS memory_meta (
                path TEXT PRIMARY KEY,
                mtime REAL NOT NULL,
                last_accessed REAL NOT NULL DEFAULT 0
            );
            """
        )
        conn.commit()

    # ------------------------------------------------------------------
    # Index building
    # ------------------------------------------------------------------

    def build_index(self) -> "MemorySearch":
        """Index all .md files in memory_dir (full rebuild)."""
        conn = self._connect()
        if not self._fts5_ok:
            return self

        conn.execute("DELETE FROM memory_fts")
        conn.execute("DELETE FROM memory_meta")

        for md_file in self._iter_md_files():
            self._index_file(conn, md_file)

        conn.commit()
        return self

    def refresh_if_stale(self) -> "MemorySearch":
        """Re-index only files whose mtime changed since last index."""
        conn = self._connect()
        if not self._fts5_ok:
            return self

        stored: dict[str, float] = {
            row["path"]: row["mtime"]
            for row in conn.execute("SELECT path, mtime FROM memory_meta")
        }

        current_paths: set[str] = set()
        for md_file in self._iter_md_files():
            path_str = str(md_file)
            current_paths.add(path_str)
            mtime = md_file.stat().st_mtime
            if stored.get(path_str) != mtime:
                conn.execute("DELETE FROM memory_fts WHERE path = ?", (path_str,))
                conn.execute("DELETE FROM memory_meta WHERE path = ?", (path_str,))
                self._index_file(conn, md_file)

        # Remove index entries for deleted files
        for stale_path in set(stored) - current_paths:
            conn.execute("DELETE FROM memory_fts WHERE path = ?", (stale_path,))
            conn.execute("DELETE FROM memory_meta WHERE path = ?", (stale_path,))

        conn.commit()
        return self

    def _iter_md_files(self):
        archive_dir = self.memory_dir / "archive"
        for md_file in self.memory_dir.rglob("*.md"):
            # Skip files inside the archive subdirectory and the DB itself
            if archive_dir in md_file.parents:
                continue
            yield md_file

    def _index_file(self, conn: sqlite3.Connection, md_file: Path) -> None:
        try:
            content = md_file.read_text(encoding="utf-8", errors="ignore")
            path_str = str(md_file)
            mtime = md_file.stat().st_mtime
            conn.execute(
                "INSERT INTO memory_fts(path, content) VALUES (?, ?)", (path_str, content)
            )
            conn.execute(
                "INSERT OR REPLACE INTO memory_meta(path, mtime, last_accessed) VALUES (?, ?, ?)",
                (path_str, mtime, 0.0),
            )
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """Return up to top_k results ranked by BM25 relevance."""
        conn = self._connect()
        if not self._fts5_ok or not query.strip():
            return []

        try:
            rows = conn.execute(
                """
                SELECT
                    path,
                    rank AS score,
                    snippet(memory_fts, 1, '[', ']', '...', 20) AS snippet
                FROM memory_fts
                WHERE memory_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, top_k),
            ).fetchall()
        except sqlite3.OperationalError:
            # Query syntax error or empty index — degrade gracefully
            return []

        now = time.time()
        results: list[SearchResult] = []
        for row in rows:
            results.append(
                SearchResult(path=row["path"], score=float(row["score"]), snippet=row["snippet"])
            )
            conn.execute(
                "UPDATE memory_meta SET last_accessed = ? WHERE path = ?",
                (now, row["path"]),
            )
        conn.commit()
        return results

    # ------------------------------------------------------------------
    # Archiving
    # ------------------------------------------------------------------

    def archive_stale(self, days: int = 90) -> int:
        """Move files not accessed in `days` days to {memory_dir}/archive/.

        Returns the count of files archived.
        """
        conn = self._connect()
        if not self._fts5_ok:
            return 0

        cutoff = time.time() - (days * 86400)
        stale_rows = conn.execute(
            "SELECT path FROM memory_meta WHERE last_accessed > 0 AND last_accessed < ?",
            (cutoff,),
        ).fetchall()

        archive_dir = self.memory_dir / "archive"
        archive_dir.mkdir(exist_ok=True)
        count = 0

        for row in stale_rows:
            src = Path(row["path"])
            if not src.exists():
                continue
            dest = archive_dir / src.name
            # Avoid collisions
            if dest.exists():
                dest = archive_dir / f"{src.stem}_{int(time.time())}{src.suffix}"
            try:
                shutil.move(str(src), str(dest))
                conn.execute("DELETE FROM memory_fts WHERE path = ?", (str(src),))
                conn.execute("DELETE FROM memory_meta WHERE path = ?", (str(src),))
                count += 1
            except OSError:
                pass

        conn.commit()
        return count

    def prune_memory_md(self, archived_paths: list[Path]) -> int:
        """Remove MEMORY.md lines that reference files that have been archived.

        Matches lines containing `](filename.md)` where filename is in archived_paths.
        Returns count of lines removed. Silently returns 0 on any I/O error.
        """
        if not archived_paths:
            return 0

        memory_md = self.memory_dir / "MEMORY.md"
        try:
            text = memory_md.read_text(encoding="utf-8")
        except OSError:
            return 0

        archived_names = {p.name for p in archived_paths}
        lines = text.splitlines(keepends=True)
        kept = []
        removed = 0
        for line in lines:
            if any(f"]({name})" in line for name in archived_names):
                removed += 1
            else:
                kept.append(line)

        if removed > 0:
            try:
                memory_md.write_text("".join(kept), encoding="utf-8")
            except OSError:
                return 0

        return removed

    def enforce_limit(self, max_active: int = 90) -> int:
        """Archive oldest-accessed memories until active count <= max_active.

        Files with last_accessed == 0 (never retrieved) are exempt — they have
        not been a retrieval hit and should not be penalised for inactivity.
        Returns count of files archived.
        """
        conn = self._connect()
        if not self._fts5_ok:
            return 0

        active_files = list(self._iter_md_files())
        if len(active_files) <= max_active:
            return 0

        excess = len(active_files) - max_active
        oldest_rows = conn.execute(
            "SELECT path FROM memory_meta"
            " WHERE last_accessed > 0 ORDER BY last_accessed ASC LIMIT ?",
            (excess,),
        ).fetchall()

        if not oldest_rows:
            return 0

        archive_dir = self.memory_dir / "archive"
        archive_dir.mkdir(exist_ok=True)
        count = 0

        for row in oldest_rows:
            src = Path(row["path"])
            if not src.exists():
                continue
            dest = archive_dir / src.name
            if dest.exists():
                dest = archive_dir / f"{src.stem}_{int(time.time())}{src.suffix}"
            try:
                shutil.move(str(src), str(dest))
                conn.execute("DELETE FROM memory_fts WHERE path = ?", (str(src),))
                conn.execute("DELETE FROM memory_meta WHERE path = ?", (str(src),))
                count += 1
            except OSError:
                pass

        conn.commit()
        return count

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "MemorySearch":
        return self

    def __exit__(self, *_) -> None:
        self.close()
