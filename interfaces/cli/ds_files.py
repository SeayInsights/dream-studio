"""ds files subcommands — artifact store queries."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def cmd_files_list(args) -> int:
    """Entry point for `ds files list`."""
    from core.files.store import list_files

    project_id = getattr(args, "project_id", None)
    category = getattr(args, "category", None)

    try:
        rows = list_files(project_id=project_id, category=category)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not rows:
        print("No files found.")
        return 0

    col_widths = {
        "file_id": 8,
        "name": 30,
        "version": 7,
        "category": 10,
        "created_at": 24,
    }

    header = (
        f"{'ID':<{col_widths['file_id']}}  "
        f"{'NAME':<{col_widths['name']}}  "
        f"{'VER':>{col_widths['version']}}  "
        f"{'CATEGORY':<{col_widths['category']}}  "
        f"{'CREATED_AT':<{col_widths['created_at']}}"
    )
    separator = "-" * len(header)
    print(header)
    print(separator)

    for row in rows:
        file_id_short = row["file_id"][:8]
        name = row["name"]
        if len(name) > col_widths["name"]:
            name = name[: col_widths["name"] - 1] + "…"
        print(
            f"{file_id_short:<{col_widths['file_id']}}  "
            f"{name:<{col_widths['name']}}  "
            f"{row['version']:>{col_widths['version']}}  "
            f"{row['category']:<{col_widths['category']}}  "
            f"{row['created_at']:<{col_widths['created_at']}}"
        )

    print(f"\n{len(rows)} file(s).")
    return 0


def add_files_subcommand(subparsers) -> None:
    """Register the 'files' subcommand group."""
    files_parser = subparsers.add_parser("files", help="Artifact store commands")
    files_sub = files_parser.add_subparsers(dest="files_cmd", required=True)

    list_parser = files_sub.add_parser("list", help="List stored artifact files")
    list_parser.add_argument(
        "--project-id",
        default=None,
        dest="project_id",
        help="Filter by project ID",
    )
    list_parser.add_argument(
        "--category",
        default=None,
        choices=["handoff", "evidence", "release", "rollback", "export"],
        help="Filter by category",
    )
    list_parser.set_defaults(func=cmd_files_list)
