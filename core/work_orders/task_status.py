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

THE SYNCHRONOUS MIRROR -- a decision, recorded where it cannot drift loose.

Seven production sites write a projected status directly beside the event they emit, so
a CLI read sees the change without waiting for the next drain. Writing the status twice
is what produced 53 work orders and 369 tasks at a status no replay could reach, so the
arrangement had to be chosen or removed rather than left unexamined.

CHOSEN: the mirror STAYS, and is accepted as deliberate duplication held by a check --
the same treatment runtime/lib/enforcement.py's second copy of this vocabulary already
gets, and for the same reason: a parity test is the correct instrument for a value that
has to exist twice.

Grounds, measured rather than argued:
  - Removing it means every read waits for a drain. `ds work-order start` followed
    immediately by `ds work-order tasks` is the common path, and the drain is not
    synchronous with either.
  - The duplication is no longer free-form. Every one of the seven now takes its value
    from `status_for(<the event this site emits>)`, so the row and the event cannot
    disagree about the word, and a renamed status is a KeyError at the write rather than
    silent drift. That removes the failure mode; it does not remove the write.
  - `test_the_guard_covers_every_writer_not_a_named_pair` DISCOVERS writers from each
    projection's declared target_tables rather than a list, so a new mirror added
    tomorrow is caught by the check rather than by the next review. The previous guard
    read two files by name and passed while seven other sites drifted.

What is NOT claimed: that the row and the event are written atomically. They are not --
the emission escapes the caller's transaction, which is WO 6935afa5 and has its own
xfail marker. This decision is about the word, not the window.
"""

from __future__ import annotations

#: Statuses meaning the task is finished. Order is not significant.
TASK_DONE_STATUSES: tuple[str, ...] = ("complete", "done")

#: Statuses meaning the task will never be finished and should not be counted as work.
TASK_ABANDONED_STATUSES: tuple[str, ...] = ("cancelled", "deleted")

#: Every status the column is known to hold, so a caller can assert it has seen them all.
TASK_STATUSES: tuple[str, ...] = TASK_DONE_STATUSES + TASK_ABANDONED_STATUSES + ("pending",)

#: The statuses a REPLAY can produce, and the legacy spellings it normalises away.
#:
#: WO 20796691. A projection rebuild reaches whatever the last handled event sets, so the
#: producible set is exactly one status per consumed event type. `done` and `open` are not
#: in it and never will be: `done` is a second spelling of `complete` (TASK_DONE_STATUSES
#: already treats them as one), and `open` is not declared vocabulary at all -- `is_open()`
#: treats an unknown status as outstanding, which is what `pending` means. 27 tasks hold
#: `done` and 10 hold `open` on the live authority; replaying their real lifecycle events
#: normalises both, which is a repair rather than a loss.
CANONICAL_TASK_STATUSES: tuple[str, ...] = ("pending", "complete", "cancelled", "deleted")

#: Legacy spelling -> the canonical status a replay produces for it.
TASK_STATUS_SYNONYMS: dict[str, str] = {"done": "complete", "open": "pending"}

#: The same for work orders. Declared HERE rather than in a test, because a vocabulary a
#: writer cannot import is not a closed set -- it is a note. `_WORK_ORDER_STATUSES` lived
#: only in tests/unit/test_status_vocabulary.py until this work order moved it.
CANONICAL_WORK_ORDER_STATUSES: tuple[str, ...] = (
    "created",
    "in_progress",
    "blocked",
    "closed",
    "cancelled",
    "deleted",
)

#: The lifecycle event that makes a replay land on each status. `created` needs no second
#: event -- the creation event alone produces it -- so it maps to None.
WORK_ORDER_STATUS_EVENT: dict[str, str | None] = {
    "created": None,
    "in_progress": "work_order.started",
    "blocked": "work_order.blocked",
    "closed": "work_order.closed",
    "cancelled": "work_order.cancelled",
    "deleted": "work_order.deleted",
}

TASK_STATUS_EVENT: dict[str, str | None] = {
    "pending": None,
    "complete": "task.completed",
    "cancelled": "task.cancelled",
    "deleted": "task.deleted",
}


#: The work-order statuses that mean the work is FINISHED and will not resume.
#:
#: WO 654a54d7, found by the review of its own fix. `_work_order_is_reopened` asked
#: `status != "closed"`, so a CANCELLED or DELETED work order read as reopened and had its
#: pinned delivery boundary widened to HEAD -- handing a grader every later commit for work
#: that had been abandoned. Closed is not the only way to finish; it is only the most
#: common one. Declared here rather than inline so the next site asking "is this work order
#: over" reads the same answer.
TERMINAL_WORK_ORDER_STATUSES: tuple[str, ...] = ("closed", "cancelled", "deleted")

#: Event -> the status a replay lands on when a projection handles it.
#:
#: THE DIRECTION A PROJECTION NEEDS, and NOT the inverse of the map above. Two events
#: produce `in_progress` -- `work_order.started` and `work_order.unblocked` -- so neither
#: map can be derived from the other: inverting status->event loses `unblocked`, and
#: inverting event->status cannot say which of the two a backfill should emit for a row
#: sitting at `in_progress`. They are two different questions that happen to share a
#: vocabulary, which is exactly the arrangement that goes wrong quietly. Both are declared,
#: and `tests/unit/test_status_vocabulary.py` fails if they disagree where they overlap.
WORK_ORDER_EVENT_STATUS: dict[str, str] = {
    "work_order.created": "created",
    "work_order.started": "in_progress",
    "work_order.unblocked": "in_progress",
    # A THIRD EVENT REACHING `in_progress`, which is why this map is declared rather than
    # inverted from the one above: reopening returns a closed work order to work, and no
    # inverse of status->event could express three events sharing one status.
    "work_order.reopened": "in_progress",
    "work_order.blocked": "blocked",
    "work_order.closed": "closed",
    "work_order.cancelled": "cancelled",
    "work_order.deleted": "deleted",
}

#: The same for tasks. `task.ac_repointed` is absent deliberately: it changes a criterion
#: and leaves the status alone, so it produces no status and must not appear here.
TASK_EVENT_STATUS: dict[str, str] = {
    "task.created": "pending",
    "task.completed": "complete",
    "task.cancelled": "cancelled",
    "task.deleted": "deleted",
}


def status_for(event_type: str, *, work_order: bool = False) -> str:
    """The status a replay lands on when this event is handled.

    THE VOCABULARY AS THE SOURCE OF THE LITERAL, not a constant sitting beside one. A
    projection that spells `SET status = 'complete'` inline has not read this module --
    the declaration and the write are two sites that agree only by inspection, which is
    the arrangement this module exists to end. Asking here means a projection CANNOT
    write a status the vocabulary does not declare, because the string only ever comes
    from the map.

    An event that produces no status raises rather than returning a default. A silent
    fallback would turn a typo'd event name into a confident write of the creation
    status, which is the shape that put 369 tasks at `cancelled` with nothing able to
    reproduce them.
    """
    mapping = WORK_ORDER_EVENT_STATUS if work_order else TASK_EVENT_STATUS
    try:
        return mapping[event_type]
    except KeyError:
        kind = "work order" if work_order else "task"
        raise KeyError(
            f"no {kind} status is produced by {event_type!r}."
            f" Events that produce one: {', '.join(sorted(mapping))}"
        ) from None


def creation_status(*, work_order: bool = False) -> str:
    """The status a freshly created row holds, named by the vocabulary rather than typed.

    Derived from the creation event rather than written out, so that moving the default
    cannot leave a projection's skeleton row writing the old one.
    """
    return status_for("work_order.created" if work_order else "task.created", work_order=work_order)


def canonical_status(status: str | None, *, work_order: bool = False) -> str:
    """The status a replay will actually land on for this row.

    A legacy spelling resolves to the canonical one it is a synonym of; anything already
    canonical is returned unchanged. An unrecognised value resolves to the creation
    default, because that is what a replay would produce for it.
    """
    value = (status or "").strip().casefold()
    if work_order:
        return value if value in CANONICAL_WORK_ORDER_STATUSES else "created"
    value = TASK_STATUS_SYNONYMS.get(value, value)
    return value if value in CANONICAL_TASK_STATUSES else "pending"


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
