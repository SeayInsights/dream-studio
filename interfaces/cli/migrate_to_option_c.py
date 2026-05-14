#!/usr/bin/env python3
"""
Migration Script: Clean up architecture to Option C

Actions:
1. Apply database schema migration
2. Create .dream-studio structure
3. Move planning files to centralized location
4. Clean up .temp folders in builds/
5. Log external repos to database
6. Create config.json
7. Verify migration
"""

import shutil
import json
from pathlib import Path
from datetime import datetime, timezone
import uuid
from core.config.database import get_connection, transaction

# Paths
HOME = Path.home()
DREAM_STUDIO_ROOT = HOME / ".dream-studio"
BUILDS_ROOT = HOME / "builds"
DREAM_STUDIO_REPO = BUILDS_ROOT / "dream-studio"
DB_PATH = DREAM_STUDIO_ROOT / "state" / "studio.db"

# New structure paths
PLANNING_ROOT = DREAM_STUDIO_ROOT / "planning"
SESSIONS_ROOT = DREAM_STUDIO_ROOT / "sessions"
TEMP_ROOT = DREAM_STUDIO_ROOT / "temp"
CACHE_ROOT = DREAM_STUDIO_ROOT / "cache"
CONFIG_PATH = DREAM_STUDIO_ROOT / "config.json"

# Backup
BACKUP_ROOT = HOME / ".dream-studio.backup.migration"


def create_backup():
    """Backup current .dream-studio and builds/ before migration"""
    print("=" * 80)
    print("STEP 1: Creating Backup")
    print("=" * 80)

    if BACKUP_ROOT.exists():
        print(f"[SKIP] Backup already exists: {BACKUP_ROOT}")
        response = input("Overwrite backup? (y/n): ")
        if response.lower() != "y":
            print("Migration cancelled")
            return False
        shutil.rmtree(BACKUP_ROOT)

    BACKUP_ROOT.mkdir(parents=True)

    # Backup .dream-studio
    if DREAM_STUDIO_ROOT.exists():
        shutil.copytree(DREAM_STUDIO_ROOT, BACKUP_ROOT / ".dream-studio")
        print(f"[OK] Backed up .dream-studio to {BACKUP_ROOT / '.dream-studio'}")

    # Backup builds/ metadata (just .planning and .temp folders)
    builds_backup = BACKUP_ROOT / "builds-metadata"
    builds_backup.mkdir()

    for item in BUILDS_ROOT.iterdir():
        if item.is_dir():
            planning = item / ".planning"
            temp = item / ".temp"
            if planning.exists() or temp.exists() or ".temp" in item.name:
                dest = builds_backup / item.name
                dest.mkdir(parents=True, exist_ok=True)
                if planning.exists():
                    shutil.copytree(planning, dest / ".planning")
                if temp.exists():
                    shutil.copytree(temp, dest / ".temp")
                print(f"[OK] Backed up metadata from {item.name}")

    print(f"\n[SUCCESS] Backup created at: {BACKUP_ROOT}")
    print("If migration fails, you can restore from this backup\n")
    return True


def apply_database_migration():
    """Apply SQL migration 004"""
    print("=" * 80)
    print("STEP 2: Applying Database Migration")
    print("=" * 80)

    migration_file = DREAM_STUDIO_REPO / "analytics" / "migrations" / "004_architecture_cleanup.sql"

    if not migration_file.exists():
        print(f"[ERROR] Migration file not found: {migration_file}")
        return False

    # Check if already applied (read-only check)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM _schema_version WHERE version = 4")
    if cursor.fetchone()[0] > 0:
        print("[SKIP] Migration 004 already applied")
        conn.close()
        return True
    conn.close()

    # Apply migration (write operation)
    try:
        with transaction() as conn:
            cursor = conn.cursor()
            sql = migration_file.read_text()
            cursor.executescript(sql)
            print("[OK] Database migration 004 applied successfully")

            # Verify tables created
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('external_repos', 'repo_analysis_log', 'cleanup_log')"
            )
            tables = cursor.fetchall()
            print(f"[OK] Created tables: {[t[0] for t in tables]}")

        return True

    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")
        return False


def create_directory_structure():
    """Create new .dream-studio structure"""
    print("\n" + "=" * 80)
    print("STEP 3: Creating Directory Structure")
    print("=" * 80)

    directories = [
        PLANNING_ROOT,
        SESSIONS_ROOT,
        TEMP_ROOT / "clones",
        TEMP_ROOT / "artifacts",
        CACHE_ROOT / "github-metadata",
        DREAM_STUDIO_ROOT / "logs",
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        print(f"[OK] {directory.relative_to(HOME)}")

    print(f"\n[SUCCESS] Directory structure created")


def migrate_planning_files():
    """Move planning files from dream-studio/.planning/specs/* to .dream-studio/planning/*"""
    print("\n" + "=" * 80)
    print("STEP 4: Migrating Planning Files")
    print("=" * 80)

    source_specs = DREAM_STUDIO_REPO / ".planning" / "specs"

    if not source_specs.exists():
        print("[SKIP] No specs folder to migrate")
        return

    moved_count = 0
    skipped_count = 0

    with transaction() as conn:
        cursor = conn.cursor()

        for project_dir in source_specs.iterdir():
            if not project_dir.is_dir():
                continue

            project_name = project_dir.name

            # Skip dream-studio's own planning and system folders
            if project_name in [
                "dream-studio",
                "ds-analytics",
                "analytics-gaps",
                "@modelcontextprotocol",
                "@upstash",
            ]:
                print(f"[SKIP] {project_name} (system folder)")
                skipped_count += 1
                continue

            # Create destination
            dest = PLANNING_ROOT / project_name / "specs"
            dest.mkdir(parents=True, exist_ok=True)

            # Move files
            for file in project_dir.iterdir():
                shutil.move(str(file), str(dest / file.name))

            # Log to cleanup_log
            cleanup_id = f"planning_{uuid.uuid4().hex[:12]}"
            cursor.execute(
                """
                INSERT INTO cleanup_log (cleanup_id, cleanup_type, source_path, destination_path, status, items_moved, cleaned_at)
                VALUES (?, 'planning_migration', ?, ?, 'success', 1, ?)
            """,
                (cleanup_id, str(project_dir), str(dest), datetime.now(timezone.utc).isoformat()),
            )

            # Update reg_projects
            cursor.execute(
                """
                UPDATE reg_projects
                SET planning_path = ?
                WHERE project_name = ? OR project_id = ?
            """,
                (str(PLANNING_ROOT / project_name), project_name, project_name.lower()),
            )

            print(
                f"[OK] Moved {project_name}: {project_dir.relative_to(HOME)} -> {dest.relative_to(HOME)}"
            )
            moved_count += 1

            # Remove empty source directory
            if project_dir.exists() and not list(project_dir.iterdir()):
                project_dir.rmdir()

    print(f"\n[SUCCESS] Migrated {moved_count} projects, skipped {skipped_count}")


def cleanup_temp_folders():
    """Find and clean up .temp folders in builds/"""
    print("\n" + "=" * 80)
    print("STEP 5: Cleaning Up .temp Folders")
    print("=" * 80)

    temp_folders = []

    # Find .temp folders
    for item in BUILDS_ROOT.iterdir():
        if item.is_dir() and ".temp" in item.name:
            temp_folders.append(item)

    # Find projects with .temp in their path (read-only check)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT project_id, project_path, project_name FROM reg_projects WHERE project_path LIKE '%.temp%'"
    )
    temp_project_records = cursor.fetchall()
    conn.close()

    print(f"Found {len(temp_folders)} .temp folders")
    print(f"Found {len(temp_project_records)} .temp project records")

    # Process temp folders and update database
    deleted_count = 0
    with transaction() as conn:
        cursor = conn.cursor()

        for folder in temp_folders:
            try:
                # Try to extract GitHub URL if it's a clone
                github_url = None
                git_config = folder / ".git" / "config"
                if git_config.exists():
                    config_text = git_config.read_text()
                    if "github.com" in config_text:
                        # Extract URL from git config
                        for line in config_text.split("\n"):
                            if "url =" in line and "github.com" in line:
                                github_url = line.split("url =")[-1].strip()
                                break

                # Log to cleanup_log
                cleanup_id = f"temp_{uuid.uuid4().hex[:12]}"
                cursor.execute(
                    """
                    INSERT INTO cleanup_log (cleanup_id, cleanup_type, source_path, status, items_deleted, cleaned_at)
                    VALUES (?, 'temp_folder', ?, 'success', 1, ?)
                """,
                    (cleanup_id, str(folder), datetime.now(timezone.utc).isoformat()),
                )

                # If GitHub repo, log to external_repos
                if github_url:
                    repo_id = f"ext_{uuid.uuid4().hex[:8]}"
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO external_repos (repo_id, github_url, clone_url, analysis_status, created_at)
                        VALUES (?, ?, ?, 'unknown', ?)
                    """,
                        (repo_id, github_url, github_url, datetime.now(timezone.utc).isoformat()),
                    )
                    print(f"[OK] Logged external repo: {github_url}")

                # Delete folder
                shutil.rmtree(folder)
                print(f"[OK] Deleted: {folder.relative_to(HOME)}")
                deleted_count += 1

            except Exception as e:
                print(f"[ERROR] Failed to delete {folder.name}: {e}")

        # Mark temp project records
        for project_id, path, name in temp_project_records:
            cursor.execute(
                """
                UPDATE reg_projects
                SET is_temp = 1, project_source = 'temp'
                WHERE project_id = ?
            """,
                (project_id,),
            )
            print(f"[OK] Marked as temp: {name}")

    print(
        f"\n[SUCCESS] Deleted {deleted_count} temp folders, marked {len(temp_project_records)} temp records"
    )


def create_config():
    """Create config.json with current setup"""
    print("\n" + "=" * 80)
    print("STEP 6: Creating Configuration")
    print("=" * 80)

    config = {
        "version": "1.0",
        "project_roots": [str(BUILDS_ROOT)],
        "temp_workspace": str(TEMP_ROOT),
        "planning_root": str(PLANNING_ROOT),
        "sessions_root": str(SESSIONS_ROOT),
        "cache_root": str(CACHE_ROOT),
        "auto_cleanup_temp": True,
        "keep_temp_days": 0,  # 0 = immediate cleanup after analysis
        "created_at": datetime.now(timezone.utc).isoformat(),
        "migration_version": 4,
    }

    CONFIG_PATH.write_text(json.dumps(config, indent=2))
    print(f"[OK] Created config: {CONFIG_PATH.relative_to(HOME)}")
    print(f"\nConfig:")
    print(json.dumps(config, indent=2))


def verify_migration():
    """Verify migration completed successfully"""
    print("\n" + "=" * 80)
    print("STEP 7: Verification")
    print("=" * 80)

    conn = get_connection()
    cursor = conn.cursor()

    checks = []

    # Check 1: Schema version
    cursor.execute("SELECT COUNT(*) FROM _schema_version WHERE version = 4")
    schema_ok = cursor.fetchone()[0] == 1
    checks.append(("Schema migration applied", schema_ok))

    # Check 2: New tables exist
    cursor.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='external_repos'"
    )
    tables_ok = cursor.fetchone()[0] == 1
    checks.append(("New tables created", tables_ok))

    # Check 3: Config exists
    config_ok = CONFIG_PATH.exists()
    checks.append(("Config.json created", config_ok))

    # Check 4: Planning directory exists
    planning_ok = PLANNING_ROOT.exists()
    checks.append(("Planning directory created", planning_ok))

    # Check 5: No .temp folders in builds/
    temp_folders = [f for f in BUILDS_ROOT.iterdir() if f.is_dir() and ".temp" in f.name]
    no_temp_ok = len(temp_folders) == 0
    checks.append(("No .temp folders in builds/", no_temp_ok))

    # Check 6: Planning files migrated
    cursor.execute(
        "SELECT COUNT(*) FROM cleanup_log WHERE cleanup_type = 'planning_migration' AND status = 'success'"
    )
    planning_migrated = cursor.fetchone()[0]
    checks.append((f"{planning_migrated} planning migrations logged", True))

    conn.close()

    # Print results
    print()
    all_passed = True
    for check, passed in checks:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {check}")
        if not passed:
            all_passed = False

    return all_passed


def print_summary():
    """Print migration summary"""
    print("\n" + "=" * 80)
    print("MIGRATION SUMMARY")
    print("=" * 80)

    conn = get_connection()
    cursor = conn.cursor()

    # Count projects
    cursor.execute("SELECT COUNT(*) FROM reg_projects WHERE project_source = 'local'")
    local_projects = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM reg_projects WHERE is_temp = 1")
    temp_projects = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM external_repos")
    external_repos = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM cleanup_log WHERE cleanup_type = 'planning_migration'")
    planning_moved = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM cleanup_log WHERE cleanup_type = 'temp_folder'")
    temp_deleted = cursor.fetchone()[0]

    conn.close()

    print(f"\nProjects:")
    print(f"  Local projects: {local_projects}")
    print(f"  Temp projects (marked): {temp_projects}")
    print(f"  External repos logged: {external_repos}")

    print(f"\nCleanup:")
    print(f"  Planning files migrated: {planning_moved}")
    print(f"  Temp folders deleted: {temp_deleted}")

    print(f"\nNew Structure:")
    print(f"  Planning: {PLANNING_ROOT.relative_to(HOME)}")
    print(f"  Sessions: {SESSIONS_ROOT.relative_to(HOME)}")
    print(f"  Temp workspace: {TEMP_ROOT.relative_to(HOME)}")
    print(f"  Config: {CONFIG_PATH.relative_to(HOME)}")

    print(f"\nBackup Location:")
    print(f"  {BACKUP_ROOT}")
    print(f"  (Safe to delete after verifying migration)")


def main():
    """Execute migration"""
    print("=" * 80)
    print("DREAM-STUDIO ARCHITECTURE MIGRATION")
    print("Option C: Centralized planning, external repos logged")
    print("=" * 80)
    print()

    # Confirm
    print("This will:")
    print("  1. Backup .dream-studio and builds/ metadata")
    print("  2. Apply database schema migration")
    print("  3. Create new .dream-studio structure")
    print("  4. Move planning files to centralized location")
    print("  5. Clean up .temp folders")
    print("  6. Create config.json")
    print()
    response = input("Continue with migration? (y/n): ")
    if response.lower() != "y":
        print("Migration cancelled")
        return 1

    # Execute steps
    if not create_backup():
        return 1

    if not apply_database_migration():
        print("\n[ERROR] Database migration failed. Check backup and try again.")
        return 1

    create_directory_structure()
    migrate_planning_files()
    cleanup_temp_folders()
    create_config()

    # Verify
    if not verify_migration():
        print("\n[WARNING] Some verification checks failed. Review above.")
        return 1

    print_summary()

    print("\n" + "=" * 80)
    print("[SUCCESS] Migration Complete!")
    print("=" * 80)
    print("\nNext steps:")
    print("  1. Verify dashboard works: py scripts/ds_dashboard.py")
    print("  2. Test project analysis with new paths")
    print("  3. Delete backup if everything works: rm -rf ~/.dream-studio.backup.migration")

    return 0


if __name__ == "__main__":
    exit(main())
