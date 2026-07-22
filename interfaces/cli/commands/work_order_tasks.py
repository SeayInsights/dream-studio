"""ds work-order command group — task-done/tasks/set-order/add-dep/remove-dep.

Split from interfaces/cli/commands/work_order.py (WO-GF-CLI-split). The
facade at interfaces/cli/commands/work_order.py re-exports this module's
private implementation helpers; interfaces/cli/commands/work_order_dispatch.py
holds the (unsplit) ``register()``/``dispatch()`` that route to them.

``_work_order_tasks`` is also imported directly (not via dispatch) by
interfaces/cli/commands/task.py's production lazy import — that import
targets the facade path (``interfaces.cli.commands.work_order``), which
re-exports this function.
"""

from __future__ import annotations

import json
from pathlib import Path


def _work_order_task_done(
    *,
    work_order_id: str,
    task_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
    planning_root: Path | None = None,
) -> int:
    from core.work_orders.mutations import mark_task_done, todowrite_should_emit

    result = mark_task_done(
        work_order_id=work_order_id,
        task_id=task_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        planning_root=planning_root,
    )
    if result.get("ok") and todowrite_should_emit(source_root):
        task_index = result.get("task_index", 0)
        todo_id = f"wo-{work_order_id[:8]}-{task_index}"
        print(json.dumps({"todowrite_update": {"id": todo_id, "status": "completed"}}, indent=2))
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _work_order_tasks(
    *,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
    verbose: bool = False,
) -> int:
    from core.work_orders.queries import list_tasks

    result = list_tasks(
        work_order_id=work_order_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        verbose=verbose,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _work_order_set_order(
    *,
    work_order_id: str,
    sequence_order: int,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.work_orders.ordering import set_sequence_order

    result = set_sequence_order(
        work_order_id=work_order_id,
        sequence_order=sequence_order,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _work_order_add_dep(
    *,
    work_order_id: str,
    depends_on_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.work_orders.ordering import add_dependency

    result = add_dependency(
        work_order_id=work_order_id,
        depends_on_id=depends_on_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _work_order_remove_dep(
    *,
    work_order_id: str,
    depends_on_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.work_orders.ordering import remove_dependency

    result = remove_dependency(
        work_order_id=work_order_id,
        depends_on_id=depends_on_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1
