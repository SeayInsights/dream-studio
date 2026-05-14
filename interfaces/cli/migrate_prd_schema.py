#!/usr/bin/env python3
"""
Data migration script for PRD schema (FR-009).

Migrates from text-based PRD tracking to relational schema:
- Scans .dream-studio/prd/ for spec.md files
- Extracts metadata and creates prd_documents entries
- Migrates raw_handoffs to prd_handoffs with prd_id linking

Usage:
    py scripts/migrate_prd_schema.py --dry-run    # Preview changes
    py scripts/migrate_prd_schema.py              # Execute migration
    py scripts/migrate_prd_schema.py --rollback   # Undo migration
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add hooks to path
sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from core.config.database import transaction  # noqa: E402


def extract_prd_id_from_path(file_path: str) -> str | None:
    """
    Extract PRD ID from file path.

    Examples:
        "prd/unified-discovery/spec.md" -> "unified-discovery"
        ".dream-studio/prd/stakeholder-pack/spec.md" -> "stakeholder-pack"
        "/full/path/prd/my-feature/spec.md" -> "my-feature"
    """
    if not file_path:
        return None

    # Match pattern: .../prd/<prd-id>/...
    match = re.search(r"/prd/([^/]+)/", file_path.replace("\\", "/"))
    if match:
        return match.group(1)

    # Fallback: .../planning/<prd-id>/... (old location)
    match = re.search(r"/planning/([^/]+)/", file_path.replace("\\", "/"))
    if match:
        return match.group(1)

    return None


def extract_frontmatter(spec_path: Path) -> dict[str, str]:
    """
    Extract metadata from spec.md frontmatter.

    Looks for YAML-style frontmatter or markdown headers:
        **Version:** 1.1
        **Status:** Approved
        **Created:** 2026-05-05
    """
    if not spec_path.exists():
        return {}

    content = spec_path.read_text(encoding="utf-8")
    metadata = {}

    # Try markdown-style metadata first
    for line in content.split("\n")[:30]:  # Check first 30 lines
        # Match: **Key:** Value
        match = re.match(r"\*\*([^:]+):\*\*\s*(.+)", line)
        if match:
            key = match.group(1).strip().lower()
            value = match.group(2).strip()

            # Clean status (remove emoji, checkmarks)
            if key == "status":
                value = re.sub(r"[✅❌🔒⏳]", "", value).strip()

            metadata[key] = value

    # Extract title from first heading if not in metadata
    if "title" not in metadata:
        match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if match:
            # Clean title (remove "PRD:" prefix, etc.)
            title = match.group(1).strip()
            title = re.sub(r"^(PRD|Spec|Feature):\s*", "", title, flags=re.IGNORECASE)
            metadata["title"] = title

    return metadata


def scan_prd_directories(prd_root: Path) -> list[dict]:
    """
    Scan .dream-studio/prd/ for PRD documents.

    Returns list of {prd_id, title, file_path, status, created_at, ...}
    """
    if not prd_root.exists():
        return []

    prds = []

    for prd_dir in prd_root.iterdir():
        if not prd_dir.is_dir():
            continue

        spec_path = prd_dir / "spec.md"
        if not spec_path.exists():
            continue

        prd_id = prd_dir.name
        metadata = extract_frontmatter(spec_path)

        # Build PRD record
        prd = {
            "prd_id": prd_id,
            "title": metadata.get("title", prd_id.replace("-", " ").title()),
            "file_path": f"prd/{prd_id}/spec.md",  # Relative to .dream-studio/
            "status": metadata.get("status", "draft").lower(),
            "created_at": metadata.get(
                "created", metadata.get("created_at", datetime.now(timezone.utc).isoformat())
            ),
            "approved_at": metadata.get("approved", metadata.get("approved_at")),
            "total_tasks": 0,  # Will be populated later
            "completed_tasks": 0,
        }

        prds.append(prd)

    return prds


def migrate_prd_documents(prds: list[dict], dry_run: bool = False):
    """Insert or update prd_documents table."""
    print(f"\n[PRD Documents] Found {len(prds)} PRDs to migrate")

    if dry_run:
        for prd in prds:
            print(f'  [DRY-RUN] Would insert: {prd["prd_id"]} - {prd["title"]}')
        return

    with transaction() as conn:
        for prd in prds:
            conn.execute(
                """
                INSERT OR REPLACE INTO prd_documents (
                    prd_id, title, file_path, status, created_at, approved_at,
                    total_tasks, completed_tasks
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    prd["prd_id"],
                    prd["title"],
                    prd["file_path"],
                    prd["status"],
                    prd["created_at"],
                    prd["approved_at"],
                    prd["total_tasks"],
                    prd["completed_tasks"],
                ),
            )

            print(f'  [OK] {prd["prd_id"]} - {prd["title"]} ({prd["status"]})')


def migrate_handoffs(dry_run: bool = False):
    """Migrate raw_handoffs to prd_handoffs."""
    # Get all handoffs with a plan_path (read-only operation)
    with transaction() as read_conn:
        handoffs = read_conn.execute("""
            SELECT id, topic, plan_path, working, broken, pending_decisions,
                   next_action, lessons_json, created_at
            FROM raw_handoffs
            WHERE plan_path IS NOT NULL
            ORDER BY id
        """).fetchall()

    print(f"\n[PRD Handoffs] Found {len(handoffs)} handoffs to migrate")

    migrated = 0
    skipped = 0

    if dry_run:
        for handoff in handoffs:
            handoff_id = handoff[0]
            plan_path = handoff[2]
            prd_id = extract_prd_id_from_path(plan_path)

            if not prd_id:
                prd_id = handoff[1] if handoff[1] else None

            if not prd_id:
                print(f'  [SKIP] Handoff #{handoff_id}: Cannot determine prd_id from "{plan_path}"')
                skipped += 1
                continue

            print(f"  [DRY-RUN] Would migrate handoff #{handoff_id} -> prd_id={prd_id}")
            migrated += 1
    else:
        with transaction() as conn:
            for handoff in handoffs:
                handoff_id = handoff[0]
                topic = handoff[1]
                plan_path = handoff[2]

                # Extract PRD ID from path
                prd_id = extract_prd_id_from_path(plan_path)

                if not prd_id:
                    # Try topic as fallback
                    prd_id = topic if topic else None

                if not prd_id:
                    print(
                        f'  [SKIP] Handoff #{handoff_id}: Cannot determine prd_id from "{plan_path}"'
                    )
                    skipped += 1
                    continue

                # Check if PRD exists
                prd_exists = conn.execute(
                    "SELECT 1 FROM prd_documents WHERE prd_id = ?", (prd_id,)
                ).fetchone()

                if not prd_exists:
                    try:
                        print(f'  [WARN] Handoff #{handoff_id}: PRD "{prd_id}" not found, skipping')
                    except UnicodeEncodeError:
                        print(
                            f"  [WARN] Handoff #{handoff_id}: PRD not found (unicode error), skipping"
                        )
                    skipped += 1
                    continue

                # Insert into prd_handoffs (preserve original handoff_id if possible)
                try:
                    conn.execute(
                        """
                        INSERT INTO prd_handoffs (
                            handoff_id, prd_id, working, broken, pending_decisions,
                            next_action, lessons_json, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            handoff_id,  # Preserve original ID
                            prd_id,
                            handoff[3],  # working
                            handoff[4],  # broken
                            handoff[5],  # pending_decisions
                            handoff[6],  # next_action
                            handoff[7],  # lessons_json
                            handoff[8],  # created_at
                        ),
                    )
                    print(f"  [OK] Handoff #{handoff_id} -> {prd_id}")
                    migrated += 1
                except sqlite3.IntegrityError as e:
                    # Handoff ID already exists, use auto-increment
                    conn.execute(
                        """
                        INSERT INTO prd_handoffs (
                            prd_id, working, broken, pending_decisions,
                            next_action, lessons_json, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            prd_id,
                            handoff[3],
                            handoff[4],
                            handoff[5],
                            handoff[6],
                            handoff[7],
                            handoff[8],
                        ),
                    )
                    new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    print(f"  [OK] Handoff #{handoff_id} -> {prd_id} (new ID: {new_id})")
                    migrated += 1

    print(f"\n[Summary] Migrated: {migrated}, Skipped: {skipped}")


def rollback_migration():
    """Delete all migrated data (rollback)."""
    print("\n[Rollback] Deleting migrated PRD data...")

    tables = [
        "prd_handoffs",
        "session_tasks",
        "prd_sessions",
        "prd_tasks",
        "prd_plans",
        "prd_documents",
    ]

    with transaction() as conn:
        for table in tables:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if count > 0:
                conn.execute(f"DELETE FROM {table}")
                print(f"  [OK] Deleted {count} rows from {table}")
            else:
                print(f"  [SKIP] {table} is empty")

    print("[OK] Rollback complete")


def main():
    parser = argparse.ArgumentParser(description="Migrate PRD schema (FR-009)")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without executing")
    parser.add_argument(
        "--rollback", action="store_true", help="Undo migration (delete all PRD data)"
    )
    args = parser.parse_args()

    if args.rollback:
        rollback_migration()
        return 0

    # Find .dream-studio/prd/ directory
    home = Path.home()
    prd_root = home / ".dream-studio" / "prd"

    if not prd_root.exists():
        print(f"[ERROR] PRD directory not found: {prd_root}")
        print("Create it with: mkdir -p ~/.dream-studio/prd")
        return 1

    print(f"[Scanning] {prd_root}")

    # Step 1: Scan and migrate PRD documents
    prds = scan_prd_directories(prd_root)
    migrate_prd_documents(prds, dry_run=args.dry_run)

    # Step 2: Migrate handoffs
    migrate_handoffs(dry_run=args.dry_run)

    # Summary
    if not args.dry_run:
        with transaction() as conn:
            prd_count = conn.execute("SELECT COUNT(*) FROM prd_documents").fetchone()[0]
            handoff_count = conn.execute("SELECT COUNT(*) FROM prd_handoffs").fetchone()[0]
            print(f"\n[Migration Complete] {prd_count} PRDs, {handoff_count} handoffs")
    else:
        print("\n[Dry-run complete] No changes made. Run without --dry-run to execute.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
