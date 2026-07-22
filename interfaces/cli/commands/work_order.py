"""ds work-order command group — work order lifecycle management.

WO-GF-CLI-split: this module is now a thin facade. ``register()``/``dispatch()``
move whole into ``work_order_dispatch`` (no decomposition needed); the
implementation helpers are grouped by concern into three content siblings —
``work_order_lifecycle`` (start/close/block/unblock), ``work_order_tasks``
(task-done/tasks/set-order/add-dep/remove-dep), and ``work_order_query``
(list/next/verify/executor/artifact/packet). Every public and private name
that used to live here is re-exported below so existing imports — including
interfaces/cli/commands/task.py's production lazy import of
``_work_order_tasks`` via this facade path — keep working unchanged.
"""

from __future__ import annotations

from interfaces.cli.commands.work_order_dispatch import dispatch, register
from interfaces.cli.commands.work_order_lifecycle import (
    _work_order_block,
    _work_order_close,
    _work_order_start,
    _work_order_unblock,
)
from interfaces.cli.commands.work_order_query import (
    _work_order_artifact,
    _work_order_executor,
    _work_order_list,
    _work_order_next,
    _work_order_packet,
    _work_order_verify,
)
from interfaces.cli.commands.work_order_tasks import (
    _work_order_add_dep,
    _work_order_remove_dep,
    _work_order_set_order,
    _work_order_task_done,
    _work_order_tasks,
)

__all__ = [
    "register",
    "dispatch",
    # work_order_lifecycle
    "_work_order_start",
    "_work_order_close",
    "_work_order_block",
    "_work_order_unblock",
    # work_order_tasks
    "_work_order_task_done",
    "_work_order_tasks",
    "_work_order_set_order",
    "_work_order_add_dep",
    "_work_order_remove_dep",
    # work_order_query
    "_work_order_list",
    "_work_order_next",
    "_work_order_verify",
    "_work_order_executor",
    "_work_order_artifact",
    "_work_order_packet",
]
