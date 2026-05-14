#!/usr/bin/env python3
"""
Database Merge Script — TA-004
Merges dream-studio.db into studio.db

Usage:
  py scripts/merge_databases.py --dry-run   # Validate only
  py scripts/merge_databases.py             # Execute merge
  py scripts/merge_databases.py --rollback  # Restore from backups
"""

import argparse
import sqlite3
import shutil
import sys
from pathlib import Path
from core.config.database import get_connection

# Database paths
STATE_DIR = Path.home() / ".dream-studio" / "state"
STUDIO_DB = STATE_DIR / "studio.db"
DREAM_STUDIO_DB = Path.home() / ".dream-studio" / "dream-studio.db"
BACKUP_DIR = Path.home() / ".dream-studio" / "backups"

# Tables to merge
TABLES_TO_MERGE = ["automation_checkpoints", "automation_log"]


def count_rows(db_path, table_name):
    """Count rows in a table"""
    if not db_path.exists():
        return 0

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except sqlite3.OperationalError:
        # Table doesn't exist in this database
        return 0


def table_exists(db_path, table_name):
    """Check if a table exists in the database"""
    if not db_path.exists():
        return False

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def merge_table(source_db, target_db, table_name, dry_run=False):
    """Merge a single table from source to target"""
    print(f"\n[{table_name}]")

    # Check if table exists in source
    if not table_exists(source_db, table_name):
        print(f"  WARNING: Table not found in source database, skipping")
        return 0, 0, 0

    # Check if table exists in target
    if not table_exists(target_db, table_name):
        print(f"  WARNING: Table not found in target database, skipping")
        return 0, 0, 0

    # Count rows before merge
    source_count = count_rows(source_db, table_name)
    target_before = count_rows(target_db, table_name)

    print(f"  Source rows: {source_count}")
    print(f"  Target rows (before): {target_before}")

    if source_count == 0:
        print(f"  No rows to merge")
        return 0, target_before, target_before

    if dry_run:
        print(f"  [DRY-RUN] Would merge {source_count} rows (duplicates will be skipped)")
        return source_count, target_before, target_before

    # Execute merge
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Attach source database
        cursor.execute("ATTACH DATABASE ? AS source", (str(source_db),))

        # Insert rows, ignoring duplicates (PK conflicts)
        cursor.execute(f"INSERT OR IGNORE INTO {table_name} SELECT * FROM source.{table_name}")
        # Note: cursor.rowcount not reliable for INSERT OR IGNORE, use count validation instead

        # Detach source database
        cursor.execute("DETACH DATABASE source")

        conn.commit()
        conn.close()

        # Count rows after merge
        target_after = count_rows(target_db, table_name)

        print(f"  Target rows (after): {target_after}")
        print(f"  Rows merged: {target_after - target_before}")
        print(f"  Duplicates skipped: {source_count - (target_after - target_before)}")

        return source_count, target_before, target_after

    except Exception as e:
        print(f"  ERROR: Error during merge: {e}")
        raise


def validate_merge(table_name, before_count, after_count, source_count):
    """Validate merge was successful"""
    if after_count < before_count:
        raise ValueError(
            f"Validation failed for {table_name}: "
            f"Target row count decreased ({before_count} -> {after_count})"
        )

    if after_count > before_count + source_count:
        raise ValueError(
            f"Validation failed for {table_name}: "
            f"Target row count increased more than source rows "
            f"({before_count} + {source_count} < {after_count})"
        )

    return True


def rollback():
    """Restore databases from backups"""
    print("=== ROLLBACK ===")
    print()

    # Check backups exist
    studio_backup = BACKUP_DIR / "studio.db.bak"
    dream_backup = BACKUP_DIR / "dream-studio.db.bak"

    if not studio_backup.exists():
        print(f"ERROR: Backup not found: {studio_backup}")
        sys.exit(1)

    if not dream_backup.exists():
        print(f"ERROR: Backup not found: {dream_backup}")
        sys.exit(1)

    # Restore studio.db
    print(f"Restoring {STUDIO_DB} from backup...")
    shutil.copy2(studio_backup, STUDIO_DB)
    print(f"  OK: Restored from {studio_backup}")

    # Restore dream-studio.db
    print(f"\nRestoring {DREAM_STUDIO_DB} from backup...")
    shutil.copy2(dream_backup, DREAM_STUDIO_DB)
    print(f"  OK: Restored from {dream_backup}")

    print("\nOK: Rollback complete")


def main():
    parser = argparse.ArgumentParser(description="Merge dream-studio.db into studio.db")
    parser.add_argument("--dry-run", action="store_true", help="Validate only, no changes")
    parser.add_argument("--rollback", action="store_true", help="Restore from backups")
    args = parser.parse_args()

    # Handle rollback mode
    if args.rollback:
        rollback()
        return

    # Display mode
    mode = "DRY-RUN" if args.dry_run else "PRODUCTION"
    print(f"=== DATABASE MERGE ({mode}) ===")
    print()
    print(f"Source: {DREAM_STUDIO_DB}")
    print(f"Target: {STUDIO_DB}")
    print()

    # Validation
    print("Validating...")

    if not STUDIO_DB.exists():
        print(f"ERROR: Target database not found: {STUDIO_DB}")
        sys.exit(1)

    if not DREAM_STUDIO_DB.exists():
        print(f"ERROR: Source database not found: {DREAM_STUDIO_DB}")
        print(f"  The audit (TA-002) indicated this database should exist with 2 tables.")
        print(f"  It may have been removed or never existed.")
        print(f"  Check: {DREAM_STUDIO_DB}")
        sys.exit(1)

    # Check backups exist
    studio_backup = BACKUP_DIR / "studio.db.bak"
    dream_backup = BACKUP_DIR / "dream-studio.db.bak"

    if not studio_backup.exists():
        print(f"WARNING: Warning: Backup not found: {studio_backup}")
        if not args.dry_run:
            print("ERROR: Cannot proceed without backups. Run TA-001 first.")
            sys.exit(1)

    if not dream_backup.exists():
        print(f"WARNING: Warning: Backup not found: {dream_backup}")
        if not args.dry_run:
            print("ERROR: Cannot proceed without backups. Run TA-001 first.")
            sys.exit(1)

    print("OK: Databases found")
    if not args.dry_run:
        print("OK: Backups verified")
    print()

    # Execute merge for each table
    total_merged = 0
    merge_results = []

    try:
        for table_name in TABLES_TO_MERGE:
            source_count, before_count, after_count = merge_table(
                DREAM_STUDIO_DB, STUDIO_DB, table_name, dry_run=args.dry_run
            )

            if not args.dry_run and source_count > 0:
                validate_merge(table_name, before_count, after_count, source_count)

            merged_count = after_count - before_count
            total_merged += merged_count
            merge_results.append((table_name, merged_count, source_count))

        # Summary
        print()
        print("=== SUMMARY ===")

        if args.dry_run:
            print("[DRY-RUN] No changes were made")
        else:
            print(f"Total rows merged: {total_merged}")

        for table_name, merged, source in merge_results:
            if source > 0:
                duplicates = source - merged
                print(f"  {table_name}: {merged} merged, {duplicates} duplicates skipped")

        print()
        if args.dry_run:
            print("OK: Dry-run validation complete")
            print("  Run without --dry-run to execute merge")
        else:
            print("OK: Merge complete")
            print(f"  Backups available at: {BACKUP_DIR}")

    except Exception as e:
        print()
        print(f"ERROR: Merge failed: {e}")
        if not args.dry_run:
            print()
            print("To rollback, run:")
            print(f"  py scripts/merge_databases.py --rollback")
        sys.exit(1)


if __name__ == "__main__":
    main()
