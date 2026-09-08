"""The one definition of what a finished milestone looks like.

WHY THIS MODULE EXISTS. The vocabulary was spelled out by hand at every site that needed
it, and the copies disagreed with the column. ``business_milestones.status`` holds
``complete`` (45 rows), ``pending`` (43) and ``deleted`` (2) -- measured 2026-09-08 --
while ``core/work_orders/milestones_classify.py`` tested membership of
``{"complete", "completed"}``. ``completed`` is a value the column has never held.

That is the same trap ``core/work_orders/task_status.py`` documents one table over:
``completed`` reads correctly, it IS correct in other tables (``scan_runs.status``,
workflow node status), and it is wrong here. A phantom member is harmless until someone
writes it, at which point every reader that omits it silently disagrees -- and a diagnostic
that hardcoded the task equivalent reported every work order 0-done.

NOT THE SAME AS A WORKFLOW STEP. ``_first_pending_step`` in that module tests step status
against ``{"complete", "completed", "skipped"}``. Steps are a different domain with their
own vocabulary and are deliberately out of scope here: unifying two vocabularies because
they share a word is how the wrong one gets applied.
"""

from __future__ import annotations

#: The status a completed milestone is written with. Named so a writer stops spelling it.
MILESTONE_COMPLETE = "complete"

#: Statuses meaning the milestone is finished.
MILESTONE_DONE_STATUSES: tuple[str, ...] = (MILESTONE_COMPLETE,)

#: Statuses meaning it will never be finished and should not be counted as work.
MILESTONE_ABANDONED_STATUSES: tuple[str, ...] = ("deleted",)

#: Every status the column is known to hold, so a caller can assert it has seen them all.
MILESTONE_STATUSES: tuple[str, ...] = (
    MILESTONE_DONE_STATUSES + MILESTONE_ABANDONED_STATUSES + ("pending",)
)


def is_complete(status: str | None) -> bool:
    """True when this status means the milestone is finished.

    Case-insensitive because the classifier lowercases before comparing and a caller that
    forgot to would otherwise get a silent False.
    """
    return (status or "").strip().lower() in MILESTONE_DONE_STATUSES


def is_open(status: str | None) -> bool:
    """True when the milestone is still outstanding work.

    Neither finished nor abandoned. An UNKNOWN status counts as open: absorbing an
    unrecognised value into "complete" is the direction that lets a milestone close over
    work nobody did.
    """
    normalised = (status or "").strip().lower()
    return normalised not in MILESTONE_DONE_STATUSES + MILESTONE_ABANDONED_STATUSES
