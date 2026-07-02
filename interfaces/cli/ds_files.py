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


def _default_artifact_name(path: Path) -> str:
    """Prefer a cwd-relative POSIX name so records stay readable and greppable."""
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.name


def cmd_files_add(args) -> int:
    """Entry point for `ds files add` — register an artifact in files.db."""
    import json
    import mimetypes
    import uuid

    from core.files.store import write_file

    path = Path(args.path)
    if not path.is_file():
        print(json.dumps({"ok": False, "error": f"not a file: {args.path}"}))
        return 1

    name = args.name or _default_artifact_name(path)
    content_type = args.content_type or mimetypes.guess_type(path.name)[0] or "text/markdown"

    try:
        content = path.read_bytes()
        file_id = write_file(
            name,
            content,
            content_type,
            args.category,
            project_id=args.project_id,
            correlation_id=str(uuid.uuid4()),
            created_by="cli",
        )
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "file_id": file_id,
                "name": name,
                "category": args.category,
                "content_type": content_type,
                "bytes": len(content),
            }
        )
    )
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

    add_parser = files_sub.add_parser(
        "add", help="Register an artifact file in the files.db docstore"
    )
    add_parser.add_argument("path", help="Path of the file to register")
    add_parser.add_argument(
        "--project-id",
        default=None,
        dest="project_id",
        help="Project ID to attach the artifact to",
    )
    add_parser.add_argument(
        "--category",
        default="evidence",
        choices=["handoff", "evidence", "release", "rollback", "export"],
        help="Artifact category (default: evidence)",
    )
    add_parser.add_argument(
        "--name",
        default=None,
        help="Stored artifact name (default: cwd-relative path of the file)",
    )
    add_parser.add_argument(
        "--content-type",
        default=None,
        dest="content_type",
        help="MIME type (default: guessed from the file name)",
    )
    add_parser.set_defaults(func=cmd_files_add)
