"""ds prd command group — the PRD + Statement-of-Work living document (WO P4).

`ds prd rescore` recomputes the derived PRD+SOW score from authority + docstore state;
`ds prd show` prints the rendered living document. See SPEC-0001 (docstore) / ADR-0003.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


def register(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    prd_cmd = subcommands.add_parser("prd", help="PRD + Statement-of-Work living document")
    prd_sub = prd_cmd.add_subparsers(dest="prd_command", required=True)

    p_rescore = prd_sub.add_parser("rescore", help="Recompute the PRD+SOW score + living document")
    p_rescore.add_argument("--project", default=None, help="Project UUID (default: active project)")

    p_show = prd_sub.add_parser("show", help="Print the PRD+SOW living document")
    p_show.add_argument("--project", default=None, help="Project UUID (default: active project)")


def dispatch(
    args: argparse.Namespace,
    *,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    if args.prd_command == "rescore":
        return _prd_rescore(
            project_id=args.project, source_root=source_root, dream_studio_home=dream_studio_home
        )
    if args.prd_command == "show":
        return _prd_show(
            project_id=args.project, source_root=source_root, dream_studio_home=dream_studio_home
        )
    print(f"Unknown prd command: {args.prd_command}", file=sys.stderr)
    return 1


def _resolve_project(
    project_id: str | None, source_root: Path, dream_studio_home: Path | None
) -> str | None:
    if project_id:
        return project_id
    from interfaces.cli.ds import resolve_installed_runtime_paths

    db_path = resolve_installed_runtime_paths(
        source_root=source_root, dream_studio_home=dream_studio_home
    ).sqlite_path
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT project_id FROM business_projects WHERE status = 'active'"
                " ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        # Missing / corrupt authority, or no business_projects table — resolve to "no active
        # project" so the caller prints an actionable message instead of a raw traceback.
        return None
    return row[0] if row else None


def _prd_rescore(
    *, project_id: str | None, source_root: Path, dream_studio_home: Path | None
) -> int:
    from core.prd.rescore import rescore_prd

    pid = _resolve_project(project_id, source_root, dream_studio_home)
    if not pid:
        print("No active project. Pass --project <id>.", file=sys.stderr)
        return 1
    result = rescore_prd(pid, source_root=source_root, dream_studio_home=dream_studio_home)
    print(
        f"PRD+SOW rescored for {pid}: overall {result['overall_score']}/100,"
        f" coverage {round(result['coverage'] * 100, 1)}%"
        f" (rendered to docstore {result['document_ref']})."
    )
    return 0


def _prd_show(*, project_id: str | None, source_root: Path, dream_studio_home: Path | None) -> int:
    from core.files.store import read_file_by_name
    from core.prd.rescore import DOC_NAME, rescore_prd

    pid = _resolve_project(project_id, source_root, dream_studio_home)
    if not pid:
        print("No active project. Pass --project <id>.", file=sys.stderr)
        return 1
    try:
        row = read_file_by_name(DOC_NAME, project_id=pid)
    except KeyError:
        row = None
    if row is None:
        # No rendered document yet — recompute it first, then print (SPEC-0001 R11).
        rescore_prd(pid, source_root=source_root, dream_studio_home=dream_studio_home)
        try:
            row = read_file_by_name(DOC_NAME, project_id=pid)
        except KeyError:
            row = None
    if row is None:
        print(f"No PRD+SOW document for project {pid}.", file=sys.stderr)
        return 1
    content = row["content"]
    if isinstance(content, (bytes, bytearray)):
        content = content.decode("utf-8")
    print(content)
    return 0
