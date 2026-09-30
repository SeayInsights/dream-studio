"""The curated MCP tool registry — projections over Dream Studio authority, read-only
today, capability-gated where a future tool mutates it.

WHY CURATED, NOT THE WHOLE CLI. `ds` exposes commands with no confirmation step by
design (an operator at a terminal is the confirmation) -- `uninstall --purge-state`,
migration execution, `review --record`, anything that mutates SQLite authority or the
filesystem. An MCP client calling this server over the network is not a terminal an
operator is watching, so every tool below ships a read path only: project/work-order
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

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Any]
    #: None (every tool below, today) means read-only: reachable by the root token or
    #: any authenticated named client, regardless of that client's own granted
    #: capabilities -- capabilities only ever gate a tool that declares one. A non-None
    #: value must be a member of integrations.mcp.auth.KNOWN_CAPABILITIES (enforced by
    #: a standing test in test_mcp_server.py, not at construction here, to keep this
    #: module free of an auth.py import it otherwise wouldn't need).
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
