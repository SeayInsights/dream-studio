"""The curated MCP tool registry — projections over Dream Studio authority, read-only
today, capability-gated where a future tool mutates it.

WHY CURATED, NOT THE WHOLE CLI. `ds` exposes commands with no confirmation step by
design (an operator at a terminal is the confirmation) -- `uninstall --purge-state`,
migration execution, `review --record`, anything that mutates SQLite authority or the
filesystem. An MCP client calling this server over the network is not a terminal an
operator is watching, so most tools below ship a read path only: project/work-order
state, review status, skills, memory, and health. Grow it from real usage, not by
mirroring the CLI surface wholesale.

A tool that mutates authority state does not get a free pass into this list just
because it declares a `required_capability` -- see `Tool.required_capability` below
and `integrations.mcp.auth.KNOWN_CAPABILITIES`. Declaring a capability is necessary,
never sufficient; it still needs the same deliberate review every tool here gets.

WHY PURE FUNCTIONS, NOT A CHILD PROCESS. Every tool here calls straight into the
same `core.*` query functions the CLI itself calls (see interfaces/cli/commands/*.py)
-- never by shelling out to `ds` as a separate process. That keeps this server in
the same process, honors the same `source_root`/`dream_studio_home` resolution the
CLI uses, and avoids a second, drifting way to invoke Dream Studio.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .auth import Identity

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Any]
    #: None (most tools below) means read-only: reachable by the root token or any
    #: authenticated named client, regardless of that client's own granted
    #: capabilities -- capabilities only ever gate a tool that declares one. A non-None
    #: value must be a member of integrations.mcp.auth.KNOWN_CAPABILITIES (enforced by
    #: a standing test in test_mcp_server.py, not at construction here -- this dataclass
    #: has no reason to validate against that set itself).
    required_capability: str | None = None


def _project_list(*, status_filter: str = "active", dream_studio_home: Path | None = None) -> Any:
    from core.projects.queries import get_project_list

    return get_project_list(
        status_filter=status_filter, source_root=REPO_ROOT, dream_studio_home=dream_studio_home
    )


def _project_state(*, dream_studio_home: Path | None = None) -> Any:
    from core.projects.queries import get_project_state

    return get_project_state(source_root=REPO_ROOT, dream_studio_home=dream_studio_home)


def _project_status(*, project_id: str, dream_studio_home: Path | None = None) -> Any:
    from core.projects.queries import get_project_status

    return get_project_status(
        project_id=project_id, source_root=REPO_ROOT, dream_studio_home=dream_studio_home
    )


def _project_create(
    *,
    name: str,
    identity: Identity,
    description: str = "",
    project_path: str | None = None,
    dream_studio_home: Path | None = None,
) -> Any:
    from core.projects.mutations_register import register_project

    result = register_project(
        name=name,
        description=description,
        project_path=Path(project_path) if project_path else None,
        source_root=REPO_ROOT,
        dream_studio_home=dream_studio_home,
    )
    # register_project does a bare INSERT, no CanonicalEventEnvelope/trace to extend
    # the way create_work_order/close_work_order have -- attribution lives only in
    # this response, the same "once, to the caller" shape ds_review_dispatch's
    # dispatched_by already uses for a function with no persisted trace of its own.
    result["registered_by"] = identity.name
    return result


def _work_order_list(
    *,
    project_id: str | None = None,
    status_filter: str | None = None,
    dream_studio_home: Path | None = None,
) -> Any:
    from core.work_orders.queries import list_work_orders

    return list_work_orders(
        project_id=project_id,
        status_filter=status_filter,
        source_root=REPO_ROOT,
        dream_studio_home=dream_studio_home,
    )


def _work_order_tasks(*, work_order_id: str, dream_studio_home: Path | None = None) -> Any:
    from core.work_orders.queries import list_tasks

    return list_tasks(
        work_order_id=work_order_id, source_root=REPO_ROOT, dream_studio_home=dream_studio_home
    )


def _require_work_order(work_order_id: str, db_path: Path) -> None:
    """Raise if `work_order_id` names no work order at all.

    `review_status()`/`open_findings()` on an unknown id return the SAME shape as a
    real, not-yet-dispatched one ("no review has been dispatched", zero findings) --
    a caller cannot tell "this id is wrong" from "this id is real but unreviewed".
    `ds review --status` already distinguishes the two (interfaces/cli/commands/
    review.py's `_show_status`); this mirrors it so the MCP tool doesn't quietly
    hand back a misleadingly clean status for a typo'd id.
    """
    from core.work_orders.review_answers import work_order_project

    if work_order_project(work_order_id, db_path=db_path) is None:
        raise ValueError(f"no work order {work_order_id!r}")


def _review_status(*, work_order_id: str, dream_studio_home: Path | None = None) -> Any:
    from core.installed_runtime import resolve_installed_runtime_paths
    from core.work_orders.review_answers import review_status

    paths = resolve_installed_runtime_paths(
        source_root=REPO_ROOT, dream_studio_home=dream_studio_home
    )
    _require_work_order(work_order_id, paths.sqlite_path)
    return review_status(work_order_id, db_path=paths.sqlite_path)


def _review_findings(*, work_order_id: str, dream_studio_home: Path | None = None) -> Any:
    from core.installed_runtime import resolve_installed_runtime_paths
    from core.work_orders.review_answers import open_findings

    paths = resolve_installed_runtime_paths(
        source_root=REPO_ROOT, dream_studio_home=dream_studio_home
    )
    _require_work_order(work_order_id, paths.sqlite_path)
    return {"open_findings": open_findings(work_order_id, db_path=paths.sqlite_path)}


def _review_dispatch(
    *,
    work_order_id: str,
    identity: Identity,
    dream_studio_home: Path | None = None,
) -> Any:
    from core.installed_runtime import resolve_installed_runtime_paths
    from core.work_orders.review_answers import dispatch_review_round

    paths = resolve_installed_runtime_paths(
        source_root=REPO_ROOT, dream_studio_home=dream_studio_home
    )
    doc = dispatch_review_round(work_order_id, repo_root=REPO_ROOT, db_path=paths.sqlite_path)
    # NOT PERSISTED -- dispatch_review_round's own stored artifact carries no actor
    # field (it predates that concept; see mutations.py's trace.mcp_client for the
    # established shape, not yet extended here). This is visible only in the response
    # handed back to whichever identity called this tool -- the same "once, to the
    # caller" reach every other value in this dict already has.
    doc["dispatched_by"] = identity.name
    return doc


def _review_run(
    *,
    work_order_id: str,
    command: str,
    identity: Identity,
    dream_studio_home: Path | None = None,
) -> Any:
    from core.installed_runtime import resolve_installed_runtime_paths
    from core.work_orders.review_answers import run_review_command

    paths = resolve_installed_runtime_paths(
        source_root=REPO_ROOT, dream_studio_home=dream_studio_home
    )
    result = run_review_command(work_order_id, command, db_path=paths.sqlite_path)
    result["run_by"] = identity.name
    return result


def _review_record(
    *,
    work_order_id: str,
    reviewer: str,
    credential: str,
    answers: list[dict[str, Any]],
    identity: Identity,
    dream_studio_home: Path | None = None,
) -> Any:
    """The recording door. `identity` is the MCP caller's own identity (what
    `review:record` gates); `reviewer`/`credential` are a SEPARATE, narrower claim --
    which named reviewer this submission is FOR, proved by record_answers' own
    per-reviewer credential check. An MCP client holding review:record can call this
    for any reviewer whose credential it happens to hold; it does not receive
    credentials it was never given (only ds_review_dispatch's caller ever sees
    those) -- the mutual-exclusion rule in the contract is what keeps the two
    separate identities apart.
    """
    from core.installed_runtime import resolve_installed_runtime_paths
    from core.work_orders.review_answers import record_answers

    paths = resolve_installed_runtime_paths(
        source_root=REPO_ROOT, dream_studio_home=dream_studio_home
    )
    result = record_answers(
        work_order_id,
        reviewer,
        answers,
        db_path=paths.sqlite_path,
        project_root=REPO_ROOT,
        credential=credential,
    )
    result["recorded_by"] = identity.name
    return result


def _work_order_task_start(
    *,
    work_order_id: str,
    task_id: str,
    identity: Identity,
    dream_studio_home: Path | None = None,
) -> Any:
    from core.work_orders.mutations import start_task

    return start_task(
        work_order_id=work_order_id,
        task_id=task_id,
        source_root=REPO_ROOT,
        dream_studio_home=dream_studio_home,
        actor=identity.name,
    )


def _work_order_task_done(
    *,
    work_order_id: str,
    task_id: str,
    identity: Identity,
    dream_studio_home: Path | None = None,
) -> Any:
    from core.work_orders.mutations import mark_task_done

    return mark_task_done(
        work_order_id=work_order_id,
        task_id=task_id,
        source_root=REPO_ROOT,
        dream_studio_home=dream_studio_home,
        actor=identity.name,
    )


def _work_order_create(
    *,
    project_id: str,
    milestone_id: str,
    title: str,
    description: str,
    identity: Identity,
    work_order_type: str | None = None,
    priority: str | None = None,
    originating_symptom: str | None = None,
    module_boundary: str | None = None,
    dream_studio_home: Path | None = None,
) -> Any:
    from core.work_orders.mutations import DEFAULT_WORK_ORDER_PRIORITY, create_work_order

    return create_work_order(
        project_id=project_id,
        milestone_id=milestone_id,
        title=title,
        description=description,
        work_order_type=work_order_type,
        priority=priority or DEFAULT_WORK_ORDER_PRIORITY,
        originating_symptom=originating_symptom,
        module_boundary=module_boundary,
        source_root=REPO_ROOT,
        dream_studio_home=dream_studio_home,
        actor=identity.name,
    )


def _work_order_close(
    *,
    work_order_id: str,
    identity: Identity,
    dream_studio_home: Path | None = None,
) -> Any:
    """Never exposes force or skip_verify -- both bypass this work order's own
    close gates, and there is no watched terminal on the other end of an MCP call
    to ask "which gates should be skipped, yes?" the way an interactive operator
    would be. A gate failure over MCP comes back as the same
    {"ok": False, "error": "Gate check failed", "failures": [...]} a CLI caller
    gets with neither flag set -- never silently waived."""
    from core.work_orders.close_main import close_work_order

    return close_work_order(
        work_order_id=work_order_id,
        force=False,
        skip_verify=False,
        source_root=REPO_ROOT,
        dream_studio_home=dream_studio_home,
        actor=identity.name,
    )


def _skill_list(*, pack_filter: str | None = None, dream_studio_home: Path | None = None) -> Any:
    from core.skills.queries import list_skills

    return list_skills(
        pack_filter=pack_filter, source_root=REPO_ROOT, dream_studio_home=dream_studio_home
    )


def _doctor(*, dream_studio_home: Path | None = None) -> Any:
    from core.health.doctor_main import run_doctor_checks

    return run_doctor_checks(source_root=REPO_ROOT, dream_studio_home=dream_studio_home, fix=False)


def _memory_query(
    *,
    text: str | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
    limit: int = 10,
    dream_studio_home: Path | None = None,
) -> Any:
    from core.config.paths import home_dir
    from core.memory.store_shared import MemoryQuery
    from core.memory.store_main import MemoryStore

    home = dream_studio_home or home_dir()
    db_path = home / "state" / "studio.db"
    store = MemoryStore(db_path=str(db_path))
    query = MemoryQuery(text=text, category=category, tags=tags, limit=limit)
    results = store.retrieve(query)
    return {
        "results": [
            {
                "memory_id": getattr(r, "memory_id", None),
                "content": getattr(r, "content", None),
                "category": getattr(r, "category", None),
                "importance": getattr(r, "importance", None),
                "relevance_score": getattr(r, "relevance_score", None),
            }
            for r in results
        ]
    }


TOOLS: list[Tool] = [
    Tool(
        name="ds_project_list",
        description=(
            "List Dream Studio projects. Read-only. Returns project id, name, status, "
            "and path for each project matching the status filter."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "status_filter": {
                    "type": "string",
                    "description": "One of active, paused, completed, archived, all. Default active.",
                }
            },
        },
        handler=_project_list,
    ),
    Tool(
        name="ds_project_state",
        description=(
            "Single-query snapshot of where work stands: the active project, the next "
            "open work order, which gates are open, and recorded gotchas. Read-only."
        ),
        input_schema={"type": "object", "properties": {}},
        handler=_project_state,
    ),
    Tool(
        name="ds_project_status",
        description="Detailed status for one project by id. Read-only.",
        input_schema={
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
        },
        handler=_project_status,
    ),
    Tool(
        name="ds_project_create",
        description=(
            "Register a new project (status 'active'). Idempotent: registering the "
            "same project_path twice returns the existing project rather than "
            "creating a duplicate. Requires project:create."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "project_path": {
                    "type": "string",
                    "description": (
                        "A path on the machine this MCP server runs on. When given, a "
                        ".dream-studio-project marker is written there so the CWD "
                        "resolver can attribute token events."
                    ),
                },
            },
            "required": ["name"],
        },
        handler=_project_create,
        required_capability="project:create",
    ),
    Tool(
        name="ds_work_order_list",
        description=(
            "List work orders, optionally filtered by project and/or status "
            "(open, in_progress, in_review, pushed, blocked, closed). Read-only."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "status_filter": {"type": "string"},
            },
        },
        handler=_work_order_list,
    ),
    Tool(
        name="ds_work_order_tasks",
        description="List the tasks under one work order by id. Read-only.",
        input_schema={
            "type": "object",
            "properties": {"work_order_id": {"type": "string"}},
            "required": ["work_order_id"],
        },
        handler=_work_order_tasks,
    ),
    Tool(
        name="ds_work_order_task_start",
        description=(
            "Move a task from created to in_progress. A claim, not a lock -- starting "
            "an already-started task is not an error. Requires work_order:task_mutate. "
            "The calling client's name is recorded on the emitted event's trace."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "work_order_id": {"type": "string"},
                "task_id": {"type": "string"},
            },
            "required": ["work_order_id", "task_id"],
        },
        handler=_work_order_task_start,
        required_capability="work_order:task_mutate",
    ),
    Tool(
        name="ds_work_order_task_done",
        description=(
            "Mark a task complete. Requires work_order:task_mutate. The calling "
            "client's name is recorded on the emitted event's trace."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "work_order_id": {"type": "string"},
                "task_id": {"type": "string"},
            },
            "required": ["work_order_id", "task_id"],
        },
        handler=_work_order_task_done,
        required_capability="work_order:task_mutate",
    ),
    Tool(
        name="ds_work_order_create",
        description=(
            "Create a work order under an existing project and milestone. Requires "
            "both to already exist (returns a clear error naming which one doesn't) "
            "-- this tool does not create either. description must describe what is "
            "being done and why (a floor, not a rubric); module_boundary is composed "
            "into it so edit attribution has a boundary to match. Requires "
            "work_order:create. The calling client's name is recorded on the "
            "emitted event's trace."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "milestone_id": {"type": "string"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "work_order_type": {"type": "string"},
                "priority": {"type": "string", "description": "Default 'normal'."},
                "originating_symptom": {"type": "string"},
                "module_boundary": {
                    "type": "string",
                    "description": "Comma-separated paths this work order owns.",
                },
            },
            "required": ["project_id", "milestone_id", "title", "description"],
        },
        handler=_work_order_create,
        required_capability="work_order:create",
    ),
    Tool(
        name="ds_work_order_close",
        description=(
            "Close a work order: evaluate its close gates, mutate status to "
            "'closed', emit events. Only from phase 'pushed' or 'ci_issues' -- "
            "refuses from any other phase. Never bypasses a gate: force and "
            "skip_verify are not exposed here, so a gate failure comes back as the "
            "same refusal a CLI caller gets with neither flag set, never silently "
            "waived. Requires work_order:close."
        ),
        input_schema={
            "type": "object",
            "properties": {"work_order_id": {"type": "string"}},
            "required": ["work_order_id"],
        },
        handler=_work_order_close,
        required_capability="work_order:close",
    ),
    Tool(
        name="ds_review_status",
        description=(
            "Whether a work order's review still blocks it: no dispatch, an "
            "unanswered lane, or an open finding. Read-only."
        ),
        input_schema={
            "type": "object",
            "properties": {"work_order_id": {"type": "string"}},
            "required": ["work_order_id"],
        },
        handler=_review_status,
    ),
    Tool(
        name="ds_review_findings",
        description="Open review findings for a work order. Read-only.",
        input_schema={
            "type": "object",
            "properties": {"work_order_id": {"type": "string"}},
            "required": ["work_order_id"],
        },
        handler=_review_findings,
    ),
    Tool(
        name="ds_review_dispatch",
        description=(
            "Convene the round table against HEAD, build the lane's Docker image, and "
            "record a new dispatch round -- issuing every named reviewer a one-time "
            "credential, returned once in this call's own response. Requires "
            "review:dispatch. The calling identity becomes the round's chair: it is "
            "the only identity that ever sees these credentials, and MUST NOT also "
            "hold review:record (refused at client-provisioning time, not here -- see "
            "integrations.mcp.auth.add_client)."
        ),
        input_schema={
            "type": "object",
            "properties": {"work_order_id": {"type": "string"}},
            "required": ["work_order_id"],
        },
        handler=_review_dispatch,
        required_capability="review:dispatch",
    ),
    Tool(
        name="ds_review_run",
        description=(
            "Run one shell command in the dispatched lane's Docker container (network "
            "isolated, no host mounts, built from the reviewed commit) and return its "
            "exit code and output. Requires review:run. UNCREDENTIALED: unlike "
            "ds_review_record, this does not check which reviewer is asking -- it is "
            "scoped only to 'a dispatch exists for this work order', not to being one "
            "of its named reviewers, so a client holding this capability can run "
            "commands against every dispatched work order at once. Weigh that "
            "independently when deciding who gets it; it is not lessened by the "
            "dispatch/record mutual-exclusion rule, which this capability sits outside."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "work_order_id": {"type": "string"},
                "command": {"type": "string"},
            },
            "required": ["work_order_id", "command"],
        },
        handler=_review_run,
        required_capability="review:run",
    ),
    Tool(
        name="ds_review_record",
        description=(
            "The recording door: submit one reviewer's answers for the current "
            "dispatch round. Every pass/finding must carry a reproduction (command + "
            "exit code); this re-runs it in a fresh container before accepting "
            "anything -- a reproduction that does not reproduce is refused, and "
            "Docker being unavailable refuses the whole submission. Requires "
            "review:record and the CREDENTIAL issued to `reviewer` at dispatch time "
            "(a separate, narrower check from the review:record capability itself: "
            "the capability says this MCP identity may call this tool at all, the "
            "credential says which specific reviewer the submission is FOR). MUST NOT "
            "be held by a client that also has review:dispatch (refused at "
            "client-provisioning time -- see integrations.mcp.auth.add_client)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "work_order_id": {"type": "string"},
                "reviewer": {"type": "string"},
                "credential": {
                    "type": "string",
                    "description": "The credential issued to this reviewer by ds_review_dispatch.",
                },
                "answers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "lane": {"type": "string"},
                            "verdict": {
                                "type": "string",
                                "enum": ["pass", "finding", "cannot-tell"],
                            },
                            "reproduction": {
                                "type": "object",
                                "properties": {
                                    "command": {"type": "string"},
                                    "exit_code": {"type": "integer"},
                                },
                            },
                            "evidence": {"type": "string"},
                            "why": {"type": "string"},
                            "check": {"type": "string"},
                            "declare": {"type": "string"},
                            "resolves_with": {"type": "string"},
                        },
                        "required": ["lane", "verdict"],
                    },
                },
            },
            "required": ["work_order_id", "reviewer", "credential", "answers"],
        },
        handler=_review_record,
        required_capability="review:record",
    ),
    Tool(
        name="ds_skill_list",
        description="List available skill packs and modes, optionally filtered by pack. Read-only.",
        input_schema={"type": "object", "properties": {"pack_filter": {"type": "string"}}},
        handler=_skill_list,
    ),
    Tool(
        name="ds_doctor",
        description=(
            "Health check: skills, agents, hooks, and routing status for the Claude "
            "Code integration plane. Read-only (never runs with --fix)."
        ),
        input_schema={"type": "object", "properties": {}},
        handler=_doctor,
    ),
    Tool(
        name="ds_memory_query",
        description=(
            "Search recorded memory (lessons, gotchas, preferences) by text, category, "
            "or tags. Read-only."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "category": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "description": "Default 10."},
            },
        },
        handler=_memory_query,
    ),
]

TOOLS_BY_NAME: dict[str, Tool] = {t.name: t for t in TOOLS}
