#!/usr/bin/env python3
"""Migrate all file-based documents to SQLite document store."""

import argparse
import sys
from pathlib import Path
import yaml
import re
from datetime import date, datetime

# Add parent directories to path for imports when run as script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from hooks.lib.document_store import DocumentStore
from hooks.lib.studio_db import _connect

# Base directory for dream-studio
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Cache of valid skill_ids and project_ids
_VALID_SKILL_IDS: set[str] | None = None
_VALID_PROJECT_IDS: set[str] | None = None


def get_valid_skill_ids() -> set[str]:
    """Get set of valid skill_ids from reg_skills table."""
    global _VALID_SKILL_IDS
    if _VALID_SKILL_IDS is None:
        with _connect() as conn:
            rows = conn.execute("SELECT skill_id FROM reg_skills").fetchall()
            _VALID_SKILL_IDS = {row[0] for row in rows}
    return _VALID_SKILL_IDS


def get_valid_project_ids() -> set[str]:
    """Get set of valid project_ids from reg_projects table."""
    global _VALID_PROJECT_IDS
    if _VALID_PROJECT_IDS is None:
        try:
            with _connect() as conn:
                rows = conn.execute("SELECT project_id FROM reg_projects").fetchall()
                _VALID_PROJECT_IDS = {row[0] for row in rows}
        except Exception:
            # Table may not exist
            _VALID_PROJECT_IDS = set()
    return _VALID_PROJECT_IDS


def validate_skill_id(skill_id: str | None) -> str | None:
    """Return skill_id if it exists in reg_skills, else None."""
    if skill_id is None:
        return None
    valid_ids = get_valid_skill_ids()
    return skill_id if skill_id in valid_ids else None


def validate_project_id(project_id: str | None) -> str | None:
    """Return project_id if it exists in reg_projects, else None."""
    if project_id is None:
        return None
    valid_ids = get_valid_project_ids()
    return project_id if project_id in valid_ids else None


def safe_yaml_load(content: str) -> dict:
    """Load YAML, converting non-JSON-serializable types to strings."""
    data = yaml.safe_load(content)
    return convert_dates_to_strings(data)


def convert_dates_to_strings(obj):
    """Recursively convert date/datetime objects to ISO format strings."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: convert_dates_to_strings(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_dates_to_strings(item) for item in obj]
    else:
        return obj


def safe_print(msg: str):
    """Print message, handling Unicode encoding errors on Windows."""
    try:
        print(msg)
    except UnicodeEncodeError:
        # Fall back to ASCII-safe version
        print(msg.encode('ascii', errors='ignore').decode('ascii'))


def parse_frontmatter(content: str) -> tuple[dict | None, str]:
    """
    Parse YAML frontmatter from markdown content.

    Returns:
        Tuple of (frontmatter_dict, content_without_frontmatter)
        If no frontmatter, returns (None, original_content)
    """
    if not content.startswith('---\n'):
        return None, content

    # Find the closing ---
    match = re.match(r'^---\n(.*?)\n---\n(.*)$', content, re.DOTALL)
    if not match:
        return None, content

    try:
        frontmatter = yaml.safe_load(match.group(1))
        body = match.group(2)
        return frontmatter, body
    except yaml.YAMLError:
        return None, content


def extract_skill_id_from_path(path: Path) -> str | None:
    """
    Extract skill_id from a path like skills/core/modes/build/SKILL.md
    Returns: 'core:build' or None
    """
    parts = path.parts
    try:
        skills_idx = parts.index('skills')
        # Check if it's a mode-based skill
        if len(parts) > skills_idx + 3 and parts[skills_idx + 2] == 'modes':
            pack = parts[skills_idx + 1]
            mode = parts[skills_idx + 3]
            return f"{pack}:{mode}"
        # Pack-level skill
        elif len(parts) > skills_idx + 1:
            pack = parts[skills_idx + 1]
            return pack
    except (ValueError, IndexError):
        pass
    return None


def migrate_skill_docs(dry_run=False) -> tuple[int, list[str]]:
    """Migrate skills/**/SKILL.md files."""
    pattern = BASE_DIR / 'skills' / '**' / 'SKILL.md'
    files = list(BASE_DIR.glob('skills/**/SKILL.md'))
    errors = []
    count = 0

    safe_print(f"[SKILL.md] Found {len(files)} files")

    for file_path in files:
        try:
            content = file_path.read_text(encoding='utf-8')
            skill_id = extract_skill_id_from_path(file_path)

            # Parse frontmatter for title
            frontmatter, body = parse_frontmatter(content)

            if frontmatter and 'ds' in frontmatter:
                ds = frontmatter['ds']
                pack = ds.get('pack', '')
                mode = ds.get('mode', '')
                title = f"{pack}:{mode}" if pack and mode else pack
            else:
                # Fallback to skill_id or path-based title
                title = skill_id or f"Skill: {file_path.parent.name}"

            if dry_run:
                safe_print(f"  [DRY-RUN] Would migrate: {file_path.relative_to(BASE_DIR)}")
                safe_print(f"    skill_id={skill_id}, title={title}")
            else:
                # Validate skill_id - only use if it exists in reg_skills
                valid_skill_id = validate_skill_id(skill_id)

                doc_id = DocumentStore.create(
                    doc_type='skill',
                    title=title,
                    content=content,
                    skill_id=valid_skill_id,
                    format='markdown',
                    metadata={
                        'file_path': str(file_path.relative_to(BASE_DIR)),
                        'frontmatter': frontmatter,
                        'original_skill_id': skill_id,  # Store original even if invalid
                    }
                )
                safe_print(f"  [OK] Migrated: {file_path.relative_to(BASE_DIR)} -> doc_id={doc_id}")

            count += 1

        except Exception as e:
            error_msg = f"Error migrating {file_path}: {e}"
            errors.append(error_msg)
            safe_print(f"  [ERROR] {error_msg}")

    return count, errors


def migrate_skill_metadata(dry_run=False) -> tuple[int, list[str]]:
    """Migrate skills/**/metadata.yml files."""
    files = list(BASE_DIR.glob('skills/**/metadata.yml'))
    errors = []
    count = 0

    safe_print(f"[metadata.yml] Found {len(files)} files")

    for file_path in files:
        try:
            content = file_path.read_text(encoding='utf-8')
            metadata = safe_yaml_load(content)
            skill_id = extract_skill_id_from_path(file_path)

            # Extract title from YAML
            title = metadata.get('name', skill_id or file_path.parent.name)

            if dry_run:
                safe_print(f"  [DRY-RUN] Would migrate: {file_path.relative_to(BASE_DIR)}")
                safe_print(f"    skill_id={skill_id}, title={title}")
            else:
                valid_skill_id = validate_skill_id(skill_id)

                doc_id = DocumentStore.create(
                    doc_type='metadata',
                    title=f"Metadata: {title}",
                    content=content,
                    skill_id=valid_skill_id,
                    format='yaml',
                    metadata={
                        'file_path': str(file_path.relative_to(BASE_DIR)),
                        'parsed': metadata,
                        'original_skill_id': skill_id,
                    }
                )
                safe_print(f"  [OK] Migrated: {file_path.relative_to(BASE_DIR)} -> doc_id={doc_id}")

            count += 1

        except Exception as e:
            error_msg = f"Error migrating {file_path}: {e}"
            errors.append(error_msg)
            safe_print(f"  [ERROR] {error_msg}")

    return count, errors


def migrate_gotchas(dry_run=False) -> tuple[int, list[str]]:
    """Migrate skills/**/gotchas.yml files."""
    files = list(BASE_DIR.glob('skills/**/gotchas.yml'))
    # Also check .dream-studio/team/gotchas.yml
    team_gotchas = BASE_DIR / '.dream-studio' / 'team' / 'gotchas.yml'
    if team_gotchas.exists():
        files.append(team_gotchas)

    errors = []
    count = 0

    safe_print(f"[gotchas.yml] Found {len(files)} files")

    for file_path in files:
        try:
            content = file_path.read_text(encoding='utf-8')
            gotchas_data = safe_yaml_load(content)

            # Extract skill_id if in skills/ directory
            skill_id = extract_skill_id_from_path(file_path) if 'skills' in file_path.parts else None

            title = f"Gotchas: {skill_id}" if skill_id else "Team Gotchas"

            if dry_run:
                safe_print(f"  [DRY-RUN] Would migrate: {file_path.relative_to(BASE_DIR)}")
                safe_print(f"    skill_id={skill_id}, title={title}")
            else:
                valid_skill_id = validate_skill_id(skill_id)

                doc_id = DocumentStore.create(
                    doc_type='gotcha',
                    title=title,
                    content=content,
                    skill_id=valid_skill_id,
                    format='yaml',
                    metadata={
                        'file_path': str(file_path.relative_to(BASE_DIR)),
                        'parsed': gotchas_data,
                        'original_skill_id': skill_id,
                    }
                )
                safe_print(f"  [OK] Migrated: {file_path.relative_to(BASE_DIR)} -> doc_id={doc_id}")

            count += 1

        except Exception as e:
            error_msg = f"Error migrating {file_path}: {e}"
            errors.append(error_msg)
            safe_print(f"  [ERROR] {error_msg}")

    return count, errors


def migrate_project_instructions(dry_run=False) -> tuple[int, list[str]]:
    """Migrate CLAUDE.md files."""
    files = []

    # Root CLAUDE.md
    root_claude = BASE_DIR / 'CLAUDE.md'
    if root_claude.exists():
        files.append(root_claude)

    # Any CLAUDE.md in skills/
    files.extend(BASE_DIR.glob('skills/**/CLAUDE.md'))

    errors = []
    count = 0

    safe_print(f"[CLAUDE.md] Found {len(files)} files")

    for file_path in files:
        try:
            content = file_path.read_text(encoding='utf-8')

            # Determine if this is root or skill-specific
            if file_path == root_claude:
                title = "Project Instructions"
                skill_id = None
            else:
                skill_id = extract_skill_id_from_path(file_path)
                title = f"Instructions: {skill_id}" if skill_id else "Instructions"

            if dry_run:
                safe_print(f"  [DRY-RUN] Would migrate: {file_path.relative_to(BASE_DIR)}")
                safe_print(f"    skill_id={skill_id}, title={title}")
            else:
                valid_skill_id = validate_skill_id(skill_id)

                doc_id = DocumentStore.create(
                    doc_type='instructions',
                    title=title,
                    content=content,
                    skill_id=valid_skill_id,
                    format='markdown',
                    metadata={
                        'file_path': str(file_path.relative_to(BASE_DIR)),
                        'original_skill_id': skill_id,
                    }
                )
                safe_print(f"  [OK] Migrated: {file_path.relative_to(BASE_DIR)} -> doc_id={doc_id}")

            count += 1

        except Exception as e:
            error_msg = f"Error migrating {file_path}: {e}"
            errors.append(error_msg)
            safe_print(f"  [ERROR] {error_msg}")

    return count, errors


def migrate_planning_specs(dry_run=False) -> tuple[int, list[str]]:
    """Migrate .planning/ directory files."""
    planning_dir = BASE_DIR / '.planning'

    if not planning_dir.exists():
        safe_print("[.planning/] Directory not found, skipping")
        return 0, []

    # Find all markdown and yaml files
    md_files = list(planning_dir.glob('**/*.md'))
    yaml_files = list(planning_dir.glob('**/*.yaml'))
    yml_files = list(planning_dir.glob('**/*.yml'))

    all_files = md_files + yaml_files + yml_files
    errors = []
    count = 0

    safe_print(f"[.planning/] Found {len(all_files)} files ({len(md_files)} .md, {len(yaml_files + yml_files)} .yaml/.yml)")

    for file_path in all_files:
        try:
            content = file_path.read_text(encoding='utf-8')

            # Extract project/topic from path: .planning/specs/<topic>/...
            relative_path = file_path.relative_to(planning_dir)
            parts = relative_path.parts

            project_id = None
            if len(parts) > 1 and parts[0] == 'specs':
                project_id = parts[1]  # e.g., 'project-intelligence'

            # Detect doc_type from filename
            filename = file_path.stem.lower()
            if filename == 'spec':
                doc_type = 'spec'
            elif filename == 'plan':
                doc_type = 'plan'
            elif filename == 'tasks':
                doc_type = 'task-plan'
            elif file_path.suffix in ['.yaml', '.yml']:
                doc_type = 'spec'  # YAML specs
            else:
                doc_type = 'planning-doc'  # Generic

            title = f"{project_id}: {filename}" if project_id else filename
            format_type = 'yaml' if file_path.suffix in ['.yaml', '.yml'] else 'markdown'

            if dry_run:
                safe_print(f"  [DRY-RUN] Would migrate: {relative_path}")
                safe_print(f"    project_id={project_id}, doc_type={doc_type}, title={title}")
            else:
                # Validate project_id - only use if it exists in reg_projects
                valid_project_id = validate_project_id(project_id)

                doc_id = DocumentStore.create(
                    doc_type=doc_type,
                    title=title,
                    content=content,
                    project_id=valid_project_id,
                    format=format_type,
                    metadata={
                        'file_path': str(relative_path),
                        'filename': file_path.name,
                        'original_project_id': project_id,
                    }
                )
                safe_print(f"  [OK] Migrated: {relative_path} -> doc_id={doc_id}")

            count += 1

        except Exception as e:
            error_msg = f"Error migrating {file_path}: {e}"
            errors.append(error_msg)
            safe_print(f"  [ERROR] {error_msg}")

    return count, errors


def migrate_building_blocks(dry_run=False) -> tuple[int, list[str]]:
    """Migrate shared/ directory if exists."""
    shared_dir = BASE_DIR / 'shared'

    if not shared_dir.exists():
        safe_print("[shared/] Directory not found, skipping")
        return 0, []

    # Find all files (excluding directories)
    all_files = [f for f in shared_dir.rglob('*') if f.is_file()]
    errors = []
    count = 0

    safe_print(f"[shared/] Found {len(all_files)} files")

    for file_path in all_files:
        try:
            # Read as binary first, try UTF-8, fall back to binary
            try:
                content = file_path.read_text(encoding='utf-8')
                is_text = True
            except UnicodeDecodeError:
                content = f"[Binary file: {file_path.name}]"
                is_text = False

            relative_path = file_path.relative_to(shared_dir)

            # Detect format from extension
            ext = file_path.suffix.lower()
            if ext == '.md':
                format_type = 'markdown'
            elif ext in ['.yaml', '.yml']:
                format_type = 'yaml'
            elif ext == '.json':
                format_type = 'json'
            elif ext in ['.py', '.js', '.ts', '.tsx', '.jsx', '.css', '.html']:
                format_type = 'code'
            else:
                format_type = 'text'

            title = f"Building Block: {relative_path}"

            if dry_run:
                safe_print(f"  [DRY-RUN] Would migrate: {relative_path}")
                safe_print(f"    format={format_type}, is_text={is_text}")
            else:
                doc_id = DocumentStore.create(
                    doc_type='building-block',
                    title=title,
                    content=content,
                    format=format_type,
                    metadata={
                        'file_path': str(relative_path),
                        'filename': file_path.name,
                        'is_binary': not is_text,
                    }
                )
                safe_print(f"  ✓ Migrated: {relative_path} → doc_id={doc_id}")

            count += 1

        except Exception as e:
            error_msg = f"Error migrating {file_path}: {e}"
            errors.append(error_msg)
            safe_print(f"  [ERROR] {error_msg}")

    return count, errors


def main():
    parser = argparse.ArgumentParser(
        description="Migrate all file-based documents to SQLite document store"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be migrated without writing to DB'
    )
    args = parser.parse_args()

    safe_print("=" * 60)
    safe_print("Document Migration to SQLite")
    safe_print("=" * 60)

    if args.dry_run:
        safe_print("[DRY-RUN MODE] No changes will be made to the database\n")
    else:
        safe_print("[LIVE MODE] Documents will be written to the database\n")

    # Track totals
    total_count = 0
    all_errors = []

    # Run all migrations
    categories = [
        ('SKILL.md files', migrate_skill_docs),
        ('metadata.yml files', migrate_skill_metadata),
        ('gotchas.yml files', migrate_gotchas),
        ('CLAUDE.md files', migrate_project_instructions),
        ('.planning/ files', migrate_planning_specs),
        ('shared/ files', migrate_building_blocks),
    ]

    for category_name, migrate_func in categories:
        safe_print(f"\n{'=' * 60}")
        safe_print(f"Migrating {category_name}...")
        print('=' * 60)

        count, errors = migrate_func(dry_run=args.dry_run)
        total_count += count
        all_errors.extend(errors)

        safe_print(f"\n{category_name}: {count} files processed")

    # Summary
    safe_print("\n" + "=" * 60)
    safe_print("MIGRATION SUMMARY")
    safe_print("=" * 60)
    safe_print(f"Total documents migrated: {total_count}")
    safe_print(f"Total errors: {len(all_errors)}")

    if all_errors:
        safe_print("\nErrors encountered:")
        for error in all_errors:
            safe_print(f"  - {error}")
        sys.exit(1)
    else:
        safe_print("\n[SUCCESS] Migration completed successfully!")
        sys.exit(0)


if __name__ == '__main__':
    main()
