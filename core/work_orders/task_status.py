"""The one definition of what a finished task looks like.

WHY THIS MODULE EXISTS. The vocabulary was written out by hand at every site that needed
it, and the copies disagreed. ``business_tasks.status`` holds ``complete`` (2,229 rows) and
``done`` (27 rows); ``core/work_orders/mutations.py`` counted remaining work with
``status NOT IN ('complete', 'cancelled')``, so a ``done`` task counted as still remaining.
Ten work orders held such a task -- all of them already closed, so the blast radius today
is zero, but the next task written as ``done`` would be miscounted by the code that feeds
the ``tasks_done`` close gate. A diagnostic in the same session hardcoded
``('done', 'completed')`` and reported EVERY work order as 0-done, because ``completed`` is
not a value this column ever holds.

``completed`` is the trap: it reads correctly, it appears in other tables
(``scan_runs.status``, workflow node status), and it is wrong here. That is why the answer
is a constant rather than a convention.

DELIBERATE DUPLICATION, AND THE TEST THAT KEEPS IT HONEST. ``runtime/lib/enforcement.py``
keeps its own copy on purpose. Not because it is stdlib-only -- it already imports
``core.event_store.event_writer`` lazily inside a ``try``, and an earlier version of this
docstring claimed otherwise -- but because it must IMPORT CLEANLY where the repo is not
importable at all: an installed adapter, or a hook fired from another project's working
directory. A module-level constant cannot be populated from a lazy import without a
hardcoded fallback, and that fallback would be this same second copy with less supervision.

So the copies are held in agreement by ``tests/unit/test_task_status_vocabulary.py``, which
fails if they diverge AND asserts that the justification still holds -- if the hook library
ever takes a module-level repo import, the copy and its parity test should both be deleted.
A parity test is the correct instrument for a constant that has to exist twice, and it is
what this repo lacked.
"""

from __future__ import annotations

#: Statuses meaning the task is finished. Order is not significant.
TASK_DONE_STATUSES: tuple[str, ...] = ("complete", "done")

#: Statuses meaning the task will never be finished and should not be counted as work.
TASK_ABANDONED_STATUSES: tuple[str, ...] = ("cancelled", "deleted")

#: Every status the column is known to hold, so a caller can assert it has seen them all.
TASK_STATUSES: tuple[str, ...] = TASK_DONE_STATUSES + TASK_ABANDONED_STATUSES + ("pending",)


def is_done(status: str | None) -> bool:
    """True when this status means the task is finished."""
    return status in TASK_DONE_STATUSES


def is_open(status: str | None) -> bool:
    """True when this status means the task is still outstanding work.

    Neither finished nor abandoned. An unknown status counts as OPEN: an unrecognised
    value must not be silently absorbed into "done", because that is the direction that
    lets a work order close over work nobody did.
    """
    return not is_done(status) and status not in TASK_ABANDONED_STATUSES


def sql_placeholders(statuses: tuple[str, ...]) -> str:
    """`?,?` for binding a status tuple, so SQL stops spelling the values inline."""
    return ",".join("?" for _ in statuses)
