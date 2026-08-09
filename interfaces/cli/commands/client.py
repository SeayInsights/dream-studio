"""ds client command group — client lifecycle (Client Layer, Attribution Coherence Phase 2).

A client owns many projects. These are thin CLI wrappers over the event-sourced core/clients
engine: create/list/show/archive/delete a client, and attach/detach a project to a client.
Mutations emit canonical events (no direct read-model writes); queries read via the resolved
authority DB.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def register(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    client = subcommands.add_parser("client", help="Manage clients (a client owns many projects)")
    client_sub = client.add_subparsers(dest="client_command", required=True)

    c_create = client_sub.add_parser("create", help="Create a client")
    c_create.add_argument("--name", required=True, help="Client name")
    c_create.add_argument("--description", default="", help="Optional description")

    c_list = client_sub.add_parser("list", help="List clients")
    c_list.add_argument(
        "--include-archived",
        action="store_true",
        default=False,
        dest="include_archived",
        help="Include archived/deleted clients",
    )

    c_show = client_sub.add_parser("show", help="Show a client + its projects")
    c_show.add_argument("client_id", help="Client id (slug)")

    c_archive = client_sub.add_parser("archive", help="Archive a client (status → archived)")
    c_archive.add_argument("client_id", help="Client id (slug)")

    c_delete = client_sub.add_parser("delete", help="Soft-delete a client (status → deleted)")
    c_delete.add_argument("client_id", help="Client id (slug)")

    c_attach = client_sub.add_parser("attach", help="Attach a project to a client")
    c_attach.add_argument("project_id", help="Project UUID")
    c_attach.add_argument("--client", required=True, dest="client_id", help="Client id (slug)")

    c_detach = client_sub.add_parser(
        "detach", help="Detach a project from its client (reassign to the SeayInsights default)"
    )
    c_detach.add_argument("project_id", help="Project UUID")

    c_fit = client_sub.add_parser(
        "fit-check",
        help="Fit proposed work against a client's projects (which project does it belong to?)",
    )
    c_fit.add_argument("--client", required=True, dest="client_id", help="Client id (slug)")
    c_fit.add_argument("--title", required=True, help="Proposed work title")
    c_fit.add_argument(
        "--description", default="", help="Proposed work description (sharpens the fit signal)"
    )


def _db_path(source_root: Path, dream_studio_home: Path | None) -> Path:
    from interfaces.cli.ds import resolve_installed_runtime_paths

    return resolve_installed_runtime_paths(
        source_root=source_root, dream_studio_home=dream_studio_home
    ).sqlite_path


def dispatch(args: argparse.Namespace, *, source_root: Path, dream_studio_home: Path | None) -> int:
    cmd = args.client_command
    if cmd == "create":
        from core.clients.mutations import create_client

        return _print(create_client(name=args.name, description=args.description))
    if cmd == "list":
        from core.clients.queries import list_clients

        db = _db_path(source_root, dream_studio_home)
        return _print(
            {
                "ok": True,
                "clients": list_clients(include_archived=args.include_archived, db_path=db),
            }
        )
    if cmd == "show":
        from core.clients.queries import get_client, projects_for_client

        db = _db_path(source_root, dream_studio_home)
        client = get_client(args.client_id, db_path=db)
        if client is None:
            return _print({"ok": False, "error": f"client not found: {args.client_id}"})
        client["projects"] = projects_for_client(args.client_id, db_path=db)
        return _print({"ok": True, "client": client})
    if cmd == "archive":
        from core.clients.mutations import archive_client

        return _print(archive_client(client_id=args.client_id))
    if cmd == "delete":
        from core.clients.mutations import delete_client

        return _print(delete_client(client_id=args.client_id))
    if cmd == "attach":
        from core.clients.mutations import assign_project_client

        return _print(assign_project_client(project_id=args.project_id, client_id=args.client_id))
    if cmd == "detach":
        from core.clients.mutations import detach_project_client

        return _print(detach_project_client(project_id=args.project_id))
    if cmd == "fit-check":
        from core.clients.queries import candidate_projects_for_work

        db = _db_path(source_root, dream_studio_home)
        return _print(
            {
                "ok": True,
                **candidate_projects_for_work(
                    args.client_id, args.title, args.description, db_path=db
                ),
            }
        )
    print(f"Unknown client command: {cmd}", file=sys.stderr)
    return 1


def _print(result: dict) -> int:
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1
