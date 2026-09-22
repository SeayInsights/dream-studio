"""ds project command group — project lifecycle management."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Parser registration
# ---------------------------------------------------------------------------


def register(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Attach the ``project`` subparser tree to *subcommands*."""
    project = subcommands.add_parser("project", help="Manage Dream Studio projects")
    project_sub = project.add_subparsers(dest="project_command", required=True)

    project_register = project_sub.add_parser("register", help="Register a new project")
    project_register.add_argument("--name", required=True, help="Project name")
    project_register.add_argument("--description", default="", help="Optional description")
    project_register.add_argument(
        "--path",
        required=True,
        metavar="DIR",
        help="Path to the project directory. A .dream-studio-project marker file will be written here.",
    )
    project_register.add_argument(
        "--client",
        default=None,
        dest="client_id",
        help="Attach the new project to this client id (default: the SeayInsights client)",
    )

    project_onboard = project_sub.add_parser(
        "onboard",
        help="Register an external project AND give it an adapter surface, in one step",
    )
    project_onboard.add_argument(
        "path", metavar="DIR", help="Path to the project directory (an existing checkout)"
    )
    project_onboard.add_argument(
        "--name", default=None, help="Project name (default: the directory's own name)"
    )
    project_onboard.add_argument(
        "--description",
        required=True,
        help=(
            "What this project is for. Required at this door because a project is the top"
            " of the same prompt chain its milestones, work orders and tasks sit in. No"
            " length floor, unlike those three: nine projects is too thin a corpus to"
            " derive one from, and one legitimate caller (brownfield intake) generates a"
            " short description on purpose."
        ),
    )
    project_onboard.add_argument(
        "--client", default=None, dest="client_id", help="Attach to this client id"
    )
    project_onboard.add_argument(
        "--plan",
        action="store_true",
        default=False,
        help="Show what would be written and change nothing -- not the repo, not the authority",
    )
    project_onboard.add_argument(
        "--git-hook",
        action="store_true",
        default=False,
        help=(
            "Also install the pre-push gate into <DIR>/.git/hooks/pre-push. OFF by default:"
            " a hook in somebody else's repository runs on every push they make, which is a"
            " thing to opt into rather than to discover."
        ),
    )

    project_list = project_sub.add_parser("list", help="List registered projects")
    project_list.add_argument(
        "--status", default="active", help="Filter by status (default: active)"
    )
    project_list.add_argument(
        "--include-deleted",
        action="store_true",
        default=False,
        dest="include_deleted",
        help="Include soft-deleted projects (status=deleted) in output",
    )
    project_list.add_argument(
        "--client",
        default=None,
        dest="client_id",
        help="List only the projects belonging to this client id",
    )
    project_list.add_argument(
        "--by-client",
        action="store_true",
        default=False,
        dest="by_client",
        help="Group all projects by client id",
    )

    project_status_cmd = project_sub.add_parser(
        "status", help="Show milestone/work-order summary for a project"
    )
    project_status_cmd.add_argument("project_id", help="Project UUID")

    project_next_cmd = project_sub.add_parser(
        "next", help="Return the first open work order for a project"
    )
    project_next_cmd.add_argument("project_id", help="Project UUID")

    project_standards_cmd = project_sub.add_parser(
        "standards", help="Show the verification standards a project declares for itself"
    )
    project_standards_cmd.add_argument(
        "--repo",
        default=None,
        help="The project tree to read (default: the current directory).",
    )

    project_set_active = project_sub.add_parser(
        "set-active", help="Set the active project in the database"
    )
    project_set_active.add_argument("project_id", help="Project UUID to activate")

    project_deactivate = project_sub.add_parser("deactivate", help="Deactivate a project")
    project_deactivate.add_argument("project_id", help="Project UUID to deactivate")

    project_start_cmd = project_sub.add_parser(
        "start", help="Activate project and start its next open work order"
    )
    project_start_cmd.add_argument("project_id", help="Project UUID")
    project_start_cmd.add_argument(
        "--planning-root",
        default=None,
        dest="planning_root",
        help="Override .planning/ directory (default: <cwd>/.planning)",
    )

    project_delete = project_sub.add_parser(
        "delete", help="Delete a project and all its dependents"
    )
    project_delete.add_argument("project_id", help="Project UUID to delete")
    project_delete.add_argument(
        "--confirm",
        action="store_true",
        default=False,
        help="Required to confirm deletion of a project with dependents",
    )

    project_state_cmd = project_sub.add_parser(
        "state",
        help="Single-query project state: active project, next WO, gates, brief, tasks, gotchas",
    )
    project_state_cmd.add_argument(
        "--planning-root",
        default=None,
        dest="planning_root",
        help="Override .planning/ directory for gate file checks (default: <cwd>/.planning)",
    )
    project_state_cmd.add_argument(
        "--full",
        action="store_true",
        default=False,
        help=(
            "Emit every ready work order instead of the first "
            f"{_READY_SET_PREVIEW}. The full set can exceed 100 entries / 96KB."
        ),
    )
    project_state_cmd.add_argument(
        "--human",
        action="store_true",
        default=False,
        help="Render a readable briefing instead of JSON",
    )

    project_fit_check = project_sub.add_parser(
        "fit-check",
        help="Fit-check proposed work against a project's open milestones (attribution guard)",
    )
    project_fit_check.add_argument("--title", required=True, help="Proposed work order title")
    project_fit_check.add_argument(
        "--description",
        default="",
        help="Proposed work order description (sharpens the fit signal)",
    )
    project_fit_check.add_argument(
        "--project-id",
        default=None,
        dest="project_id",
        help="Project UUID (default: the globally-active project)",
    )


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def dispatch(
    args: argparse.Namespace,
    *,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    if args.project_command == "register":
        return _project_register(
            name=args.name,
            description=args.description,
            project_path=Path(args.path).resolve(),
            client_id=getattr(args, "client_id", None),
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.project_command == "onboard":
        return _project_onboard(
            path=Path(args.path),
            name=args.name,
            description=args.description,
            client_id=getattr(args, "client_id", None),
            plan_only=args.plan,
            git_hook=args.git_hook,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.project_command == "list":
        return _project_list(
            status_filter=args.status,
            include_deleted=getattr(args, "include_deleted", False),
            client_id=getattr(args, "client_id", None),
            by_client=getattr(args, "by_client", False),
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.project_command == "status":
        return _project_status(
            project_id=args.project_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.project_command == "next":
        return _project_next(
            project_id=args.project_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.project_command == "set-active":
        return _project_set_active(
            project_id=args.project_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.project_command == "deactivate":
        return _project_deactivate(
            project_id=args.project_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.project_command == "delete":
        return _project_delete(
            project_id=args.project_id,
            confirm=args.confirm,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.project_command == "start":
        planning_root = Path(args.planning_root).resolve() if args.planning_root else None
        return _project_start(
            project_id=args.project_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
            planning_root=planning_root,
        )
    if args.project_command == "standards":
        return _project_standards(getattr(args, "repo", None))

    if args.project_command == "state":
        planning_root = Path(args.planning_root).resolve() if args.planning_root else None
        return _project_state(
            source_root=source_root,
            dream_studio_home=dream_studio_home,
            planning_root=planning_root,
            full=getattr(args, "full", False),
            human=getattr(args, "human", False),
        )
    if args.project_command == "fit-check":
        return _project_fit_check(
            work_title=args.title,
            work_description=args.description,
            project_id=args.project_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    print(f"Unknown project command: {args.project_command}", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------


def _project_register(
    *,
    name: str,
    description: str,
    project_path: Path,
    client_id: str | None = None,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.projects.mutations import register_project

    result = register_project(
        name=name,
        description=description,
        project_path=project_path,
        client_id=client_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if result.get("ok"):
        result["hint"] = (
            f"To make this the active project, run: ds project set-active {result['project_id']}"
        )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _project_fit_check(
    *,
    work_title: str,
    work_description: str,
    project_id: str | None,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.projects.queries import fit_check_work_order

    result = fit_check_work_order(
        work_title=work_title,
        work_description=work_description,
        project_id=project_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _project_onboard(
    *,
    path: Path,
    name: str | None,
    description: str,
    client_id: str | None,
    plan_only: bool,
    git_hook: bool,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    """Register an external project and give it an adapter surface, in one step.

    BOTH HALVES WERE ALREADY BUILT AND NEVER JOINED. `ds project register` writes the
    authority row and the `.dream-studio-project` marker. `ds integrate install` writes
    the adapter surface -- but only into the directory it is run from or the operator's
    home, because `detect_claude_code` derives the config root from the working directory
    and nothing let a caller name a different one.

    So a project could be registered, carry work orders, and have nothing on disk telling
    an agent working inside it that Dream Studio exists. Measured: Dream Command had 14
    work orders in the authority and no adapter surface in its checkout.

    Neither half is reimplemented here. This resolves the target, calls both, and reports
    what each did -- including when the second fails after the first succeeded, because a
    half-onboarded project that reports success is worse than one that reports the truth.
    """
    from integrations.detector import detect_claude_code
    from integrations.installer.claude_code import ClaudeCodeInstaller
    from integrations.manifest import get_ds_home

    from core.projects.mutations import register_project

    target = Path(path).expanduser().resolve()
    if not target.is_dir():
        # REFUSED BEFORE ANYTHING IS WRITTEN. A typo here would otherwise register a
        # project whose path points at nothing, and the CWD resolver would then attribute
        # none of its work -- a failure that surfaces much later as missing telemetry.
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"Not a directory: {target}",
                    "remedy": "onboard an existing checkout",
                },
                indent=2,
            )
        )
        return 1

    detected = detect_claude_code(working_dir=target, scope_override="project")
    installer = ClaudeCodeInstaller(
        detected.config_root,
        "project",
        canonical_root=source_root / "canonical",
        ds_home=dream_studio_home or get_ds_home(),
        git_repo_root=(target if git_hook else None),
    )

    if plan_only:
        # A PLAN CHANGES NOTHING, AND THAT INCLUDES THE AUTHORITY. Registering the project
        # and only pretending about the files would be the worse half of a dry run: the
        # part that is hard to undo done, the part you can see not done.
        print(
            json.dumps(
                {
                    "ok": True,
                    "mode": "plan",
                    "project_path": str(target),
                    "config_root": str(detected.config_root),
                    "would_register": {"name": name or target.name, "description": description},
                    "git_hook": git_hook,
                    "plan": installer.plan().summary(),
                },
                indent=2,
                default=str,
            )
        )
        return 0

    # Registration first, and it is idempotent by path -- re-onboarding a project already
    # in the authority returns the existing row rather than a duplicate, which is what
    # makes this usable on the projects that have the row and not the surface.
    registered = register_project(
        name=name or target.name,
        description=description,
        project_path=target,
        client_id=client_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not registered.get("ok"):
        print(json.dumps({"ok": False, "stage": "register", **registered}, indent=2))
        return 1

    try:
        installed = installer.install("execute")
    except Exception as exc:  # noqa: BLE001 - the partial state is the thing to report
        print(
            json.dumps(
                {
                    "ok": False,
                    "stage": "install",
                    "error": str(exc),
                    "project_id": registered["project_id"],
                    "registered": True,
                    "config_root": str(detected.config_root),
                    "remedy": (
                        "the project IS registered; re-run `ds project onboard` to retry the"
                        " adapter surface, or `ds integrate install claude_code --scope"
                        f" project` from {target}"
                    ),
                },
                indent=2,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "project_id": registered["project_id"],
                "name": registered["name"],
                "project_path": str(target),
                "marker_written": registered.get("marker_written"),
                "config_root": str(detected.config_root),
                "git_hook": git_hook,
                "install": installed,
                "hint": (
                    "To make this the active project, run:"
                    f" ds project set-active {registered['project_id']}"
                ),
            },
            indent=2,
            default=str,
        )
    )
    return 0


def _project_list(
    *,
    status_filter: str,
    include_deleted: bool = False,
    client_id: str | None = None,
    by_client: bool = False,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    # --client / --by-client reuse the client engine's read side, which is safe on a
    # pre-migration-155 DB (returns no rows / '(unassigned)' rather than erroring).
    if client_id or by_client:
        from interfaces.cli.ds import resolve_installed_runtime_paths

        db_path = resolve_installed_runtime_paths(
            source_root=source_root, dream_studio_home=dream_studio_home
        ).sqlite_path
        try:
            if by_client:
                from core.clients.queries import projects_grouped_by_client

                result = {
                    "ok": True,
                    "grouped_by_client": projects_grouped_by_client(db_path=db_path),
                }
            else:
                from core.clients.queries import projects_for_client

                result = {
                    "ok": True,
                    "client_id": client_id,
                    "projects": projects_for_client(client_id, db_path=db_path),
                }
        except Exception as exc:
            result = {"ok": False, "error": f"client listing unavailable: {exc}"}
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    from core.projects.queries import get_project_list

    result = get_project_list(
        status_filter=status_filter,
        include_deleted=include_deleted,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _project_status(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.projects.queries import get_project_status

    result = get_project_status(
        project_id=project_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _project_next(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.projects.queries import get_next_work_order

    result = get_next_work_order(
        project_id=project_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _project_set_active(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.projects.mutations import set_active_project

    result = set_active_project(
        project_id=project_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _project_deactivate(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.projects.mutations import deactivate_project

    result = deactivate_project(
        project_id=project_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _project_start(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
    planning_root: Path | None = None,
) -> int:
    """CLI wrapper around `core.projects.start.start_project`.

    Converts the composer's compound result dict into the legacy
    operator-facing output: the inner `work_order_start` JSON on stdout
    (so tests that parse it still work), then a human-readable summary
    with the project name, work-order title, type/milestone, context.md
    path, task count, and close hint.
    """

    from core.projects.start import start_project

    result = start_project(
        project_id=project_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        planning_root=planning_root,
    )

    if not result.get("ok"):
        print(json.dumps(result))
        return 1

    project_name = result.get("project_name", project_id)

    if result.get("no_open_work_orders"):
        print(
            f"Project activated: {project_name}\n"
            "No open work orders found.\n"
            f"Run `ds project next {project_id}` to check status."
        )
        return 0

    next_wo = result.get("next_work_order") or {}
    wo_id = next_wo.get("work_order_id", "")
    wo_title = next_wo.get("title", "")
    wo_type = next_wo.get("work_order_type") or "—"
    milestone_str = next_wo.get("milestone") or "—"
    # WO-FILESDB-C2: context lives in the authority; show the read command when it
    # was stored there (context_path is None), else the legacy disk-fallback path.
    if result.get("context_in_authority"):
        context_loaded = f"authority — `ds work-order artifact {wo_id} context`"
    else:
        context_loaded = result.get("context_path") or ""
    task_count = result.get("tasks_count", 0)
    tasks_str = f"{task_count} tasks queued" if task_count else "tasks queued"

    # Preserve the legacy operator surface: the inner work-order start JSON
    # was previously printed by _work_order_start before the summary.
    wo_start = result.get("work_order_start") or {}
    print(json.dumps(wo_start, indent=2))

    print(
        f"\nProject activated: {project_name}\n"
        f"Starting: {wo_title}\n"
        f"Type: {wo_type} | Milestone: {milestone_str}\n"
        f"\nContext loaded: {context_loaded}\n"
        f"Tasks ready: {tasks_str}\n"
        f"\nRun `ds work-order close {wo_id}` when done."
    )
    return 0


def _project_delete(
    *,
    project_id: str,
    confirm: bool,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    """CLI wrapper around ``core.projects.mutations.delete_project``.

    The CLI ``--confirm`` flag maps to the function's ``confirm=True``
    kwarg. The function returns a dict whose error path mentions
    ``confirm=True`` (the kwarg name); the wrapper post-processes the
    message to use ``--confirm`` (the operator-facing flag name) so the
    CLI error text stays as it was before A6.3 lifted the function.
    """

    from core.projects.mutations import delete_project

    result = delete_project(
        project_id=project_id,
        confirm=confirm,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not result.get("ok"):
        error = result.get("error", "")
        if "Pass confirm=True" in error:
            result = {**result, "error": error.replace("Pass confirm=True", "Pass --confirm")}
        print(json.dumps(result))
        return 1
    print(json.dumps(result))
    return 0


def _project_state(
    *,
    source_root: Path,
    dream_studio_home: Path | None,
    planning_root: Path | None = None,
    full: bool = False,
    human: bool = False,
) -> int:
    """Single-call project state: active project + next WO + gates + brief + tasks + gotchas.

    `ready_set` is every unblocked work order on a project. On a mature project
    that is the whole backlog: measured at 132 entries / 96KB for one project,
    inside a 151,683-character response. That is the dominant term in the output
    and it is emitted at every session start, so it costs the operator's reading
    attention and the model's context window on every single orientation.

    So the default response previews the ready set and reports its true size.
    `--full` restores the complete list for anything that needs to enumerate it,
    and `--human` renders a briefing instead of JSON.
    """
    from core.projects.queries import get_project_state

    result = get_project_state(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        planning_root=planning_root,
    )
    # Client Layer context: surface the active project's client. Guarded — business_projects.client_id
    # exists only after migration 155, so on a pre-155 DB this stays None rather than erroring.
    try:
        import sqlite3 as _sqlite3

        from interfaces.cli.ds import resolve_installed_runtime_paths

        db = resolve_installed_runtime_paths(
            source_root=source_root, dream_studio_home=dream_studio_home
        ).sqlite_path
        conn = _sqlite3.connect(str(db))
        try:
            has_col = any(
                r[1] == "client_id" for r in conn.execute("PRAGMA table_info(business_projects)")
            )
            if has_col:
                row = conn.execute(
                    "SELECT client_id FROM business_projects WHERE status = 'active' LIMIT 1"
                ).fetchone()
                result["active_client_id"] = row[0] if row else None
        finally:
            conn.close()
    except Exception:
        pass

    if not full:
        _preview_ready_sets(result)
    if human:
        print(_render_state_briefing(result))
    else:
        print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


_READY_SET_PREVIEW = 5


def _preview_ready_sets(result: dict) -> None:
    """Trim each project's ready_set in place, recording what was omitted.

    The key stays a list so existing readers keep working; two sibling keys make
    the truncation explicit rather than silently under-reporting the backlog.
    """
    for project in result.get("projects") or []:
        ready = project.get("ready_set")
        if not isinstance(ready, list):
            continue
        project["ready_set_total"] = len(ready)
        if len(ready) > _READY_SET_PREVIEW:
            project["ready_set"] = ready[:_READY_SET_PREVIEW]
            project["ready_set_truncated"] = True
            project["ready_set_hint"] = (
                f"showing {_READY_SET_PREVIEW} of {len(ready)} ready work orders; "
                "re-run with --full for the complete list"
            )
        else:
            project["ready_set_truncated"] = False


def _render_state_briefing(result: dict) -> str:
    """A readable orientation: what is active, what is next, what is in the way."""
    out: list[str] = []
    projects = result.get("projects") or []

    if not projects:
        return "No registered projects."

    for project in projects:
        name = project.get("name") or "(unnamed)"
        status = project.get("status") or "?"
        out.append(f"{name}  [{status}]")

        wo = project.get("next_work_order") or {}
        if wo:
            done = (wo.get("total_tasks") or 0) - (wo.get("pending_tasks") or 0)
            out.append(
                f"  next: {wo.get('title') or '(untitled)'}"
                f"  ({wo.get('status')}, {done}/{wo.get('total_tasks') or 0} tasks)"
            )
            brief = wo.get("design_brief") or {}
            if brief:
                out.append(
                    f"  brief: {brief.get('status')}"
                    f" ({brief.get('fields_filled')}/{brief.get('fields_total')} fields)"
                )
            warn = wo.get("test_execution_warning")
            if warn:
                out.append(f"  warning: {warn}")
            for g in wo.get("gotchas") or []:
                out.append(f"  gotcha: {g}")
        else:
            out.append("  next: (nothing ready)")

        total = project.get("ready_set_total")
        if total is None:
            total = len(project.get("ready_set") or [])
        out.append(f"  ready set: {total} unblocked work order(s)")

        risks = project.get("unverified_risks") or {}
        if risks.get("total"):
            out.append(f"  unverified risks: {risks['total']}")

        action = project.get("next_action")
        if action:
            out.append(f"  -> {action}")
        out.append("")

    ci = result.get("main_ci") or {}
    if ci.get("red"):
        out.append(f"main CI: RED — {ci.get('title') or ci.get('head_sha') or 'unknown'}")
        if ci.get("run_url"):
            out.append(f"  {ci['run_url']}")
    elif ci.get("status"):
        out.append(f"main CI: {ci.get('status')}")

    bypass = result.get("bypass_summary") or {}
    if bypass.get("last_7d_total"):
        out.append(f"bypasses (7d): {bypass['last_7d_total']}")

    return "\n".join(out).rstrip()


def _project_standards(repo: str | None) -> int:
    """Print the resolved standards profile for a tree.

    An absent profile is an ANSWER, not an error: it means pytest, which is what every
    project got before profiles existed. Printing it that way is the point -- an operator
    debugging a refused check needs to see which of the three states they are in without
    reading the module.
    """
    from pathlib import Path as _Path

    from core.projects.standards import declared_test_profile, is_pytest, standards_path

    root = _Path(repo).resolve() if repo else _Path.cwd()
    path = standards_path(root)
    profile = declared_test_profile(root)

    print(f"project: {root}")
    print(f"profile: {path}{'' if path and path.is_file() else '  (absent)'}")

    command = profile.get("command")
    if not command:
        print("tests:   pytest (declared nothing, so the default applies)")
        return 0

    print(f"tests:   {command}")
    if is_pytest(command):
        print("         recognised as pytest, so a bare TEST-CHECK node id runs as usual")
        return 0

    with_target = profile.get("with_target")
    if with_target:
        print(f"one test: {with_target}")
        return 0

    print(
        "one test: NOT DECLARED -- a bare TEST-CHECK node id is refused here, because"
        " Dream Studio cannot guess how this runner takes one test. Write the check as"
        " `TEST-CHECK: cmd: <command>`, or add a `with_target` line."
    )
    return 0
