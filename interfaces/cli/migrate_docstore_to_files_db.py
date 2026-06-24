#!/usr/bin/env python3
"""Migrate ds_documents rows from studio.db into files.db.

Three-store architecture fix: ds_documents belongs in files.db (the document/
artifact store), not in studio.db (the canonical event authority).  This script
is idempotent - rows that already exist in files.db (matched by doc_id) are
skipped, so it is safe to re-run.

Usage:
    py interfaces/cli/migrate_docstore_to_files_db.py           # apply
    py interfaces/cli/migrate_docstore_to_files_db.py --dry-run # preview only
    py interfaces/cli/migrate_docstore_to_files_db.py --verbose  # detailed output
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.config.paths import state_dir
from core.files.store import connect_files, ensure_files_schema
from core.storage.document_store import ensure_documents_schema

_COPY_COLUMNS = (
    "doc_id",
    "doc_type",
    "parent_doc_id",
    "project_id",
    "skill_id",
    "session_id",
    "title",
    "content",
    "format",
    "metadata",
    "tags",
    "keywords",
    "version",
    "status",
    "created_at",
    "created_by",
    "updated_at",
    "access_count",
    "last_accessed",
    "ttl_days",
    "expires_at",
)

_PLACEHOLDERS = ", ".join("?" for _ in _COPY_COLUMNS)
_COL_LIST = ", ".join(_COPY_COLUMNS)


def migrate(
    studio_db_path: Path,
    files_db_path: Path,
    *,
    dry_run: bool = False,
    verbose: bool = False,
) -> dict:
    """Copy rows from studio.db ds_documents -> files.db ds_documents.

    Returns a summary dict with keys: copied, skipped, total_in_source.
    """
    if not studio_db_path.exists():
        return {"ok": False, "error": f"studio.db not found at {studio_db_path}"}

    src = sqlite3.connect(str(studio_db_path))
    src.row_factory = sqlite3.Row

    # Check that ds_documents exists in studio.db
    table_exists = src.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='ds_documents'"
    ).fetchone()[0]
    if not table_exists:
        src.close()
        return {
            "ok": True,
            "copied": 0,
            "skipped": 0,
            "total_in_source": 0,
            "note": "ds_documents does not exist in studio.db - nothing to migrate",
        }

    rows = src.execute(f"SELECT {_COL_LIST} FROM ds_documents").fetchall()  # noqa: S608
    src.close()

    total = len(rows)
    if verbose:
        print(f"Found {total} rows in studio.db ds_documents")

    if dry_run:
        print(f"[dry-run] Would copy {total} rows from studio.db -> files.db ds_documents")
        return {"ok": True, "dry_run": True, "total_in_source": total}

    dst = connect_files(files_db_path)
    try:
        ensure_files_schema(dst)
        ensure_documents_schema(dst)

        copied = 0
        skipped = 0

        for row in rows:
            doc_id = row["doc_id"]
            existing = dst.execute(
                "SELECT 1 FROM ds_documents WHERE doc_id = ?", (doc_id,)
            ).fetchone()
            if existing:
                if verbose:
                    print(f"  skip doc_id={doc_id} (already in files.db)")
                skipped += 1
                continue

            values = tuple(row[col] for col in _COPY_COLUMNS)
            dst.execute(
                f"INSERT INTO ds_documents ({_COL_LIST}) VALUES ({_PLACEHOLDERS})",  # noqa: S608
                values,
            )
            if verbose:
                print(f"  copy doc_id={doc_id} doc_type={row['doc_type']!r} title={row['title']!r}")
            copied += 1

        # Rebuild FTS index for all copied rows to ensure search works
        if copied > 0:
            dst.execute("INSERT INTO ds_documents_fts(ds_documents_fts) VALUES ('rebuild')")

        dst.commit()
    finally:
        dst.close()

    print(
        f"Migration complete: {copied} copied, {skipped} skipped " f"(total {total} rows in source)"
    )
    return {"ok": True, "copied": copied, "skipped": skipped, "total_in_source": total}


def _verify_files_db(files_db_path: Path) -> dict:
    """Verify ds_documents rows are readable from files.db and FTS works."""
    if not files_db_path.exists():
        return {"ok": False, "error": "files.db does not exist"}

    conn = connect_files(files_db_path)
    try:
        ensure_files_schema(conn)
        ensure_documents_schema(conn)
        count = conn.execute("SELECT COUNT(*) FROM ds_documents").fetchone()[0]
        # Test FTS with a broad query (first 3 words of any title)
        fts_ok = True
        try:
            conn.execute(
                "SELECT COUNT(*) FROM ds_documents d "
                "INNER JOIN ds_documents_fts f ON d.doc_id = f.rowid"
            ).fetchone()
        except Exception:
            fts_ok = False
        return {"ok": True, "row_count": count, "fts_ok": fts_ok}
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Migrate ds_documents from studio.db to files.db (idempotent)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument(
        "--studio-db",
        type=Path,
        default=None,
        help="Path to studio.db (default: ~/.dream-studio/state/studio.db)",
    )
    parser.add_argument(
        "--files-db",
        type=Path,
        default=None,
        help="Path to files.db (default: ~/.dream-studio/state/files.db)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="After migration, verify rows are in files.db",
    )
    args = parser.parse_args(argv)

    studio_db = args.studio_db or (state_dir() / "studio.db")
    files_db = args.files_db or (state_dir() / "files.db")

    print(f"Source: {studio_db}")
    print(f"Target: {files_db}")

    result = migrate(
        studio_db,
        files_db,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    if not result.get("ok"):
        print(f"ERROR: {result.get('error')}", file=sys.stderr)
        return 1

    if args.verify and not args.dry_run:
        print("\nVerifying files.db ...")
        vr = _verify_files_db(files_db)
        if vr.get("ok"):
            print(f"  rows in files.db ds_documents: {vr['row_count']}")
            print(f"  FTS functional: {vr['fts_ok']}")
            if vr["row_count"] == 0:
                print("  WARNING: 0 rows - check that studio.db had rows to copy")
        else:
            print(f"  VERIFY FAILED: {vr.get('error')}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
