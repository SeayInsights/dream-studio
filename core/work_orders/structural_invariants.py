"""Two structural invariants, checked where they can actually be judged.

Operator ruling: a work order should ALWAYS have multiple tasks; a milestone should
ALWAYS have more than one work order. Measured on the live authority 2026-08-28 using the
counting below — every task and every sibling, not only the open ones: of 128 open work
orders, 49 carry one task or none and 4 sit in a milestone with no sibling. 52 distinct
work orders would be refused at close.

WHY NOT AT CREATION, despite the task saying "at creation". A work order has zero tasks
at the moment it is created -- always, for every work order that has ever been correct. A
milestone has zero work orders. A creation-time check would refuse everything or refuse
nothing; it cannot tell a badly-sized unit from a correctly-sized one that is one second
old.

WHY NOT AT START EITHER, which is where this was built first. ds-project decomposes only
the first work order of the first milestone, and its own instructions say the rest "get
tasks when they are started (by calling start_work_order())". So a work order legitimately
arrives at start with zero tasks and acquires them a moment later. Refusing there blocked
the documented authoring path -- measured, it broke 18 existing tests whose fixtures seed a
work order and no tasks, which is exactly the shape start is supposed to accept.

SO: START REPORTS, CLOSE REFUSES. Close is where "this work order is done" gets claimed.
One task then is not a not-yet; it is a finished unit that was mis-sized, and the count is
a fact. Start still says so, because the author is about to write tasks and that is the
cheapest possible moment to hear that one is not enough.

NEVER SILENTLY ALLOW. The escape is not a bare flag -- ``--force`` bypasses every gate at
once and records no reasoning about this one. It is a REASON, stored as an
``operator_decision`` artifact, so an exception is something a later reader can find and
weigh rather than an absence they cannot see.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

MIN_TASKS_PER_WORK_ORDER = 2
MIN_WORK_ORDERS_PER_MILESTONE = 2

EXCEPTION_KIND = "operator_decision"
EXCEPTION_KEY = "structure_exception"


@dataclass(frozen=True)
class Violation:
    """One broken invariant, with the command that would satisfy it.

    ``scope`` is ``"work_order"`` or ``"milestone"``. ``message`` always names a fix,
    because a refusal that only states the problem leaves the author to guess -- and the
    guess most people reach for is the escape hatch.
    """

    scope: str
    found: int
    required: int
    message: str


def _connect(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def _unevaluated(exc: Exception) -> Violation:
    """The gate could not read the data. Blocks, and says why."""
    return Violation(
        scope="unevaluated",
        found=-1,
        required=-1,
        message=(
            f"The structural invariants could not be evaluated: "
            f"{type(exc).__name__}: {exc}. This BLOCKS rather than passes — a gate that "
            f"cannot read its data has not found the work order clean, it has found "
            f"nothing. If this database predates the business_tasks table, record why "
            f"this work order is exempt with --accept-structure."
        ),
    )


def _authority_created(conn: sqlite3.Connection, work_order_id: str) -> bool | None:
    """Did the authority author this work order? ``None`` when it cannot be told.

    True only when a ``work_order.created`` canonical event names it. False for a row
    someone inserted directly. None when the canonical event table is absent, which means
    this database is not a Dream Studio authority at all -- and a gate about how the
    authority sizes work has nothing to say about a database that is not one.

    None and False are both "do not judge", but they are different facts and a later
    reader should be able to tell them apart, so they are not collapsed into a bool.
    """
    try:
        row = conn.execute(
            "SELECT 1 FROM business_canonical_events"
            " WHERE event_type = 'work_order.created'"
            "   AND json_extract(trace, '$.work_order_id') = ?"
            " LIMIT 1",
            (work_order_id,),
        ).fetchone()
    except sqlite3.Error:
        return None
    return row is not None


def check_structure(work_order_id: str, *, db_path: Path) -> list[Violation]:
    """Return the invariants this work order breaks, empty when it breaks none.

    Counts EVERY task and EVERY sibling work order, not just open ones. A milestone whose
    other work orders are all closed still had more than one; judging it by what remains
    open would call a finished milestone malformed.

    A work order with no milestone is not judged on the milestone invariant -- there is
    nothing to count, and inventing a verdict from missing data is the failure this
    repository keeps finding elsewhere.
    """
    violations: list[Violation] = []
    try:
        conn = _connect(db_path)
    except sqlite3.Error as exc:
        return [_unevaluated(exc)]

    try:
        # ONLY WORK ORDERS THE AUTHORITY CREATED ARE JUDGED (operator ruling 2026-08-30).
        #
        # The invariant is about how a human or agent SIZES real work. Applied to every
        # close path it also caught hermetic test fixtures, which are one-task by design
        # because they are exercising some other gate. Measured: it broke 23 tests on main
        # across 10 files, and repairing them meant adding setup unrelated to what each
        # test was about -- one such addition then broke four more, because a seeded
        # acceptance criterion is not inert.
        #
        # `create_work_order` emits `work_order.created`; a row inserted by raw SQL emits
        # nothing. That event is therefore the exact, recorded line between a work order
        # the authority authored and a row someone put in a table -- no heuristic, and no
        # new column. It is not an evasion route either: a row with no event is deleted by
        # the next projection rebuild, so raw-SQL work orders do not survive to be closed.
        #
        # Measured on the live authority the day this was scoped: 101 of 132 open work
        # orders are event-backed and 45 of those still break an invariant, so the gate
        # keeps almost all of its reach (45 of 49) while fixtures fall outside it.
        if _authority_created(conn, work_order_id) is not True:
            return violations

        row = conn.execute(
            "SELECT milestone_id FROM business_work_orders WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if row is None:
            # The work order is not projected yet. Nothing to judge, and refusing here
            # would block a work order that was created seconds ago.
            return violations
        milestone_id = row[0]

        tasks = conn.execute(
            "SELECT COUNT(*) FROM business_tasks WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()[0]
        if tasks < MIN_TASKS_PER_WORK_ORDER:
            violations.append(
                Violation(
                    scope="work_order",
                    found=tasks,
                    required=MIN_TASKS_PER_WORK_ORDER,
                    message=(
                        f"This work order carries {tasks} task(s); a work order carries at "
                        f"least {MIN_TASKS_PER_WORK_ORDER}. A single-task work order is a "
                        f"task wearing the wrong label: it closes on one check and gets "
                        f"almost no verification. Add tasks with "
                        f"`ds work-order add-task {work_order_id} --title ... "
                        f"--acceptance TEST-CHECK:...`, or split the work order."
                    ),
                )
            )

        if milestone_id:
            siblings = conn.execute(
                "SELECT COUNT(*) FROM business_work_orders WHERE milestone_id = ?",
                (milestone_id,),
            ).fetchone()[0]
            if siblings < MIN_WORK_ORDERS_PER_MILESTONE:
                violations.append(
                    Violation(
                        scope="milestone",
                        found=siblings,
                        required=MIN_WORK_ORDERS_PER_MILESTONE,
                        message=(
                            f"Milestone {milestone_id[:8]} carries {siblings} work "
                            f"order(s); a milestone carries at least "
                            f"{MIN_WORK_ORDERS_PER_MILESTONE}. A one-work-order milestone "
                            f"is a work order with extra ceremony -- it cannot sequence "
                            f"anything and its close gates grade a single diff twice. Add "
                            f"work orders with `ds work-order create <project_id> "
                            f"--milestone {milestone_id} --title ...`, or fold this work "
                            f"into a milestone that has siblings."
                        ),
                    )
                )
    except sqlite3.Error as exc:
        # A GATE THAT CANNOT EVALUATE MUST NOT REPORT CLEAN. This returned [] -- no
        # violations -- so a database error silently PASSED the gate, on exactly the work
        # orders whose data is broken. An independent review caught it, and it is the
        # absent-is-not-clean error this repository keeps finding, committed by the very
        # module written to enforce the opposite.
        #
        # An old schema without business_tasks lands here too, so the message says which
        # it cannot tell apart and names the escape rather than stranding the operator.
        return [_unevaluated(exc)]
    finally:
        conn.close()

    return violations


def recorded_exception(work_order_id: str, *, db_path: Path) -> str | None:
    """The recorded reason this work order is allowed to break an invariant, or None."""
    from .artifacts import get_wo_artifact

    return get_wo_artifact(
        work_order_id, EXCEPTION_KIND, instance_key=EXCEPTION_KEY, db_path=db_path
    )


def record_exception(work_order_id: str, reason: str, *, db_path: Path) -> bool:
    """Record why this work order may break a structural invariant.

    The reason is required and must say something. An empty or one-word reason is refused
    -- "n/a" recorded in the authority is worse than no exception at all, because it looks
    like a decision was made.
    """
    from .artifacts import set_wo_artifact

    text = (reason or "").strip()
    if len(text) < 12:
        raise ValueError(
            "A structural exception needs a reason a later reader can weigh. "
            "Say why this work order is correctly sized despite the invariant."
        )
    # A RECORDED REASON THAT WAS NOT RECORDED IS WORSE THAN NO ESCAPE AT ALL. Both callers
    # (start_work_order and the close CLI) catch only ValueError, so a False return meant
    # --accept-structure printed success, stored nothing, and the next close refused with
    # the identical message -- leaving the operator to conclude the flag does not work.
    # Raise instead: an escape hatch must either take effect or say it did not.
    # EVERY STORAGE FAILURE ARRIVES AS ValueError, because that is the contract both
    # callers already handle -- `start_main.start_work_order` and the close CLI each
    # `except ValueError`. Once `set_wo_artifact` learned to RAISE on a lock instead of
    # silently returning False, a busy authority turned `--accept-structure` into an
    # unhandled `sqlite3.OperationalError` traceback at both sites: the handled case was
    # the rare one and the likely one crashed. An independent review measured it
    # (WO b302834b task fe18ee64).
    #
    # Converted here rather than widened at each caller, so a third caller cannot
    # reintroduce it, and because "the exception could not be recorded" is one fact
    # however SQLite chose to report it.
    try:
        stored = set_wo_artifact(
            work_order_id,
            EXCEPTION_KIND,
            text,
            instance_key=EXCEPTION_KEY,
            db_path=db_path,
        )
    except sqlite3.Error as exc:
        raise ValueError(
            f"The structural exception could not be recorded ({type(exc).__name__}: "
            f"{exc}). Without the record the close gate will refuse again with the same "
            f"message, so the reason has to land before --accept-structure means "
            f"anything. If the authority is busy, re-run this once it is writable."
        ) from exc
    if not stored:
        raise ValueError(
            "The structural exception could not be recorded: this authority's schema "
            "predates the artifact table. Without the record the close gate will refuse "
            "again, so the reason has to land before --accept-structure means anything. "
            "Release the migration with `ds migrate activate`, then re-run."
        )
    return True


def render(violations: list[Violation], work_order_id: str, *, refusing: bool = True) -> str:
    """The violation text, in the voice of the moment it is said.

    Start reports and proceeds; close refuses. Same violations, different consequence, so
    the text must not claim a refusal that is not happening -- a warning phrased as a
    refusal teaches people that refusals are survivable.
    """
    body = "\n\n".join(f"  - {v.message}" for v in violations)
    if not refusing:
        return (
            f"{len(violations)} structural invariant(s) are not met yet:\n\n{body}\n\n"
            f"This does not block the start — a work order is often decomposed into tasks "
            f"immediately after starting. It DOES block the close, so satisfy it while "
            f"that is still the natural next thing to do."
        )
    return (
        f"structural_invariants: {len(violations)} invariant(s) not met:\n\n{body}\n\n"
        f"If this work order is correctly sized despite that, record why:\n"
        f'  ds work-order close {work_order_id} --accept-structure "<reason>"\n'
        f"The reason is stored on the work order, so the exception is something a later "
        f"reader can find and weigh. `--force` is not the answer: it bypasses every gate "
        f"at once and records no reasoning about this one."
    )
