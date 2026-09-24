"""The curated MCP tool registry — read-only projections over Dream Studio authority.

WHY CURATED, NOT THE WHOLE CLI. `ds` exposes commands with no confirmation step by
design (an operator at a terminal is the confirmation) -- `uninstall --purge-state`,
migration execution, `review --record`, anything that mutates SQLite authority or the
filesystem. An MCP client calling this server over the network is not a terminal an
operator is watching, so this registry ships only read paths: project/work-order
state, review status, skills, memory, and health. Grow it from real usage, not by
mirroring the CLI surface wholesale.

WHY PURE FUNCTIONS, NOT SUBPROCESS. Every tool here calls straight into the same
`core.*` query functions the CLI itself calls (see interfaces/cli/commands/*.py) --
no `subprocess.run(["ds", ...])`. That keeps this server in the same process, honors
the same `source_root`/`dream_studio_home` resolution the CLI uses, and avoids a
second, drifting way to invoke Dream Studio.
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


def _review_status(*, work_order_id: str, dream_studio_home: Path | None = None) -> Any:
    from core.installed_runtime import resolve_installed_runtime_paths
    from core.work_orders.review_answers import review_status

    paths = resolve_installed_runtime_paths(
        source_root=REPO_ROOT, dream_studio_home=dream_studio_home
    )
    return review_status(work_order_id, db_path=paths.sqlite_path)


def _review_findings(*, work_order_id: str, dream_studio_home: Path | None = None) -> Any:
    from core.installed_runtime import resolve_installed_runtime_paths
    from core.work_orders.review_answers import open_findings

    paths = resolve_installed_runtime_paths(
        source_root=REPO_ROOT, dream_studio_home=dream_studio_home
    )
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
