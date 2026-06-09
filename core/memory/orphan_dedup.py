"""Deduplicate NULL-source_type memory_entries that have a content-matched
keyed counterpart. Surfaced by 18.4.5 design review (D3); first-run side-effect
of GotchaIngestionConsumer creating properly-keyed entries alongside legacy
NULL-source_type entries with identical content.

Conservative deletion: only removes NULL entries that have a keyed match.
NULL entries without a match are preserved (other sources may legitimately
have NULL source_type — e.g., manually-added entries).

FTS note: migration 079 creates memory_entries_fts_delete to keep memory_fts
in sync. If those triggers are absent (verified via PF-3), this module deletes
from memory_fts explicitly before deleting from memory_entries. Either path
leaves FTS correct.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field


@dataclass(frozen=True)
class DedupResult:
    """Summary of an orphan dedup pass."""

    candidates_found: int
    deleted: int
    preserved_null: int  # NULL entries with no content match
    errors: list[str] = field(default_factory=list)


def _has_fts_delete_trigger(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='trigger' AND name='memory_entries_fts_delete'"
    ).fetchone()
    return row is not None


def _has_memory_fts(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE name='memory_fts'").fetchone()
    return row is not None


def find_orphan_candidates(conn: sqlite3.Connection) -> list[str]:
    """Return memory_id values that are safe to delete.

    A row is a candidate IFF:
      - source_type IS NULL, AND
      - there exists at least one OTHER row with the same content AND
        source_type IS NOT NULL
    """
    rows = conn.execute("""
        SELECT m.memory_id
        FROM memory_entries m
        WHERE m.source_type IS NULL
          AND EXISTS (
              SELECT 1
              FROM memory_entries other
              WHERE other.source_type IS NOT NULL
                AND other.content = m.content
                AND other.memory_id != m.memory_id
          )
        """).fetchall()
    return [row[0] for row in rows]


def count_unmatched_nulls(conn: sqlite3.Connection) -> int:
    """Count NULL entries with no keyed counterpart (these are preserved)."""
    row = conn.execute("""
        SELECT COUNT(*)
        FROM memory_entries m
        WHERE m.source_type IS NULL
          AND NOT EXISTS (
              SELECT 1
              FROM memory_entries other
              WHERE other.source_type IS NOT NULL
                AND other.content = m.content
                AND other.memory_id != m.memory_id
          )
        """).fetchone()
    return int(row[0]) if row else 0


def dedup_orphans(conn: sqlite3.Connection, dry_run: bool = True) -> DedupResult:
    """Run the dedup pass. Idempotent: second call finds zero candidates.

    dry_run=True returns candidate count without deleting (default).
    dry_run=False commits deletions; handles FTS sync explicitly since
    memory_entries_fts_delete trigger may be absent.
    """
    errors: list[str] = []
    candidates = find_orphan_candidates(conn)
    preserved = count_unmatched_nulls(conn)

    if dry_run or not candidates:
        return DedupResult(
            candidates_found=len(candidates),
            deleted=0,
            preserved_null=preserved,
            errors=errors,
        )

    # Migration 082 (18.4.5-followup-2) defensively restores memory_entries_fts_delete.
    # This manual sync path should not fire on any DB that has run migration 082.
    # Retained for resilience against unmigrated databases or future trigger loss.
    needs_manual_fts = _has_memory_fts(conn) and not _has_fts_delete_trigger(conn)

    deleted = 0
    BATCH = 200
    for i in range(0, len(candidates), BATCH):
        chunk = candidates[i : i + BATCH]  # noqa: E203
        placeholders = ",".join("?" * len(chunk))
        try:
            if needs_manual_fts:
                # FTS delete trigger absent — sync manually before row deletion
                conn.execute(
                    f"DELETE FROM memory_fts WHERE memory_id IN ({placeholders})",
                    chunk,
                )
            conn.execute(
                f"DELETE FROM memory_entries WHERE memory_id IN ({placeholders})",
                chunk,
            )
            deleted += len(chunk)
        except sqlite3.Error as exc:
            errors.append(f"batch {i}-{i + len(chunk)}: {exc}")

    conn.commit()
    return DedupResult(
        candidates_found=len(candidates),
        deleted=deleted,
        preserved_null=preserved,
        errors=errors,
    )
