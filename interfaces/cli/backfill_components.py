"""Backfill pi_components table with Python components from registered projects.

Usage:
    python backfill_components.py                  # Process all registered projects
    python backfill_components.py --project-id foo # Process specific project only
"""

from __future__ import annotations

import argparse
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from core.event_store import studio_db
from projections.graph import component_extractor
from tqdm import tqdm

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Directories to skip when scanning for Python files
SKIP_DIRS = {
    "venv",
    ".venv",
    "env",
    ".env",
    "node_modules",
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "build",
    "dist",
    ".tox",
    ".coverage",
}


def get_registered_projects() -> list[dict]:
    """Query reg_projects table for all registered projects.

    Returns:
        List of project dicts with project_id, project_path, etc.
    """
    try:
        projects = studio_db.list_projects()
        logger.info(f"Found {len(projects)} registered projects")
        return projects
    except Exception as e:
        logger.error(f"Failed to query registered projects: {e}")
        return []


def scan_python_files(project_path: Path) -> list[Path]:
    """Find all .py files in project_path, skipping venv and .git.

    Args:
        project_path: Root directory to scan

    Returns:
        List of Path objects for all Python files found
    """
    if not project_path.exists():
        logger.warning(f"Project path does not exist: {project_path}")
        return []

    if not project_path.is_dir():
        logger.warning(f"Project path is not a directory: {project_path}")
        return []

    python_files = []

    try:
        for file_path in project_path.rglob("*.py"):
            # Skip if any parent directory is in SKIP_DIRS
            if any(part in SKIP_DIRS for part in file_path.parts):
                continue
            python_files.append(file_path)

        logger.info(f"Found {len(python_files)} Python files in {project_path}")
        return python_files

    except Exception as e:
        logger.error(f"Failed to scan {project_path}: {e}")
        return []


def process_single_file(file_path: Path, project_id: str, project_root: Path) -> tuple[int, bool]:
    """Extract components from a single Python file.

    Args:
        file_path: Path to Python file
        project_id: Project identifier
        project_root: Project root for relative path calculation

    Returns:
        Tuple of (component_count, had_error)
    """
    try:
        components = component_extractor.extract_components(
            file_path, project_id, project_root=project_root
        )

        if components:
            component_extractor.save_to_db(components)

        return len(components), False

    except Exception as e:
        logger.error(f"Failed to process {file_path.name}: {e}")
        return 0, True


def process_project(project_id: str, project_path: Path) -> None:
    """Extract components for all .py files in a project.

    Args:
        project_id: Project identifier
        project_path: Project root directory
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Processing project: {project_id}")
    logger.info(f"Path: {project_path}")
    logger.info(f"{'='*60}")

    # Scan for Python files
    python_files = scan_python_files(project_path)

    if not python_files:
        logger.info(f"{project_id}: No Python files found")
        return

    total_components = 0
    total_errors = 0

    # Process files in parallel with progress bar
    with ThreadPoolExecutor(max_workers=4) as executor:
        # Submit all tasks
        futures = {
            executor.submit(process_single_file, file_path, project_id, project_path): file_path
            for file_path in python_files
        }

        # Progress bar
        with tqdm(total=len(python_files), desc=f"Processing {project_id}") as pbar:
            for future in as_completed(futures):
                file_path = futures[future]
                pbar.set_description(f"Processing {file_path.name}")

                component_count, had_error = future.result()
                total_components += component_count
                if had_error:
                    total_errors += 1

                pbar.update(1)

    # Log summary
    logger.info(
        f"\n{project_id}: {total_components} components extracted, " f"{total_errors} parse errors"
    )


def main() -> None:
    """Main entry point for backfill script."""
    parser = argparse.ArgumentParser(
        description="Backfill pi_components table from registered projects"
    )
    parser.add_argument(
        "--project-id",
        type=str,
        help="Process only this project (default: all registered projects)",
    )
    args = parser.parse_args()

    if args.project_id:
        # Process specific project
        logger.info(f"Processing single project: {args.project_id}")

        project = studio_db.get_project(args.project_id)
        if not project:
            logger.error(f"Project not found in registry: {args.project_id}")
            sys.exit(1)

        project_path = Path(project["project_path"])
        process_project(args.project_id, project_path)

    else:
        # Process all registered projects
        logger.info("Processing all registered projects")

        projects = get_registered_projects()
        if not projects:
            logger.warning("No registered projects found")
            sys.exit(0)

        for project in projects:
            project_id = project["project_id"]
            project_path = Path(project["project_path"])

            process_project(project_id, project_path)

    logger.info("\n" + "=" * 60)
    logger.info("Backfill complete")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
