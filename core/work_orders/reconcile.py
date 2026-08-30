"""What the authority says is open but the work says is finished.

Task 4 of WO-WO-LIFECYCLE-SURFACE. Measured on the live authority 2026-08-28: 13 open work
orders have every task complete, 25 open milestones have no open work order, and 4 work
orders have been in_progress since May.

WHY THIS MATTERS MORE THAN IT LOOKS. Status that drifts makes every other count
untrustworthy -- including the counts this very milestone is measured by. "49 of 128 open
work orders carry one task or none" is only a fact if "open" means something; if a tenth of
the open set is actually finished, every ratio quoted from it is quietly wrong, and the
gates built on those ratios inherit the error.

DRIFT IS REPORTED, NEVER AUTO-RESOLVED. Closing a work order runs gates -- independent
review, executable ACs, the structural invariants -- and a reconciler that closed things on
the operator's behalf would be bypassing all of them for exactly the work orders nobody has
looked at recently. That is the opposite of what a reconciler is for. This surfaces the
candidates and names the command; a human runs it.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

# A work order in_progress for longer than this has almost certainly been abandoned rather
# than worked on. Not a rule -- a prompt to look.
STALE_DAYS = 30

_OPEN_WO = "('created', 'in_progress')"
_DONE_TASK = "('complete', 'cancelled')"


@dataclass
class Drift:
    """Everything the authority holds open that looks finished."""

    completable_work_orders: list[dict] = field(default_factory=list)
    completable_milestones: list[dict] = field(default_factory=list)
    stale_in_progress: list[dict] = field(default_factory=list)

    @property
    def total(self) -> int:
        return (
            len(self.completable_work_orders)
            + len(self.completable_milestones)
            + len(self.stale_in_progress)
        )

    def render(self) -> str:
        if self.total == 0:
            return "reconcile: nothing has drifted — every open record still has open work."

        lines: list[str] = [
            f"reconcile: {self.total} record(s) the authority holds open that look finished.",
            "",
        ]
        if self.completable_work_orders:
            lines.append(
                f"{len(self.completable_work_orders)} work order(s) with every task complete:"
            )
            for row in self.completable_work_orders:
                lines.append(f"  {row['work_order_id'][:8]}  {_label(row['title'], 58)}")
                lines.append(f"      ds work-order close {row['work_order_id']}")
            lines.append("")
        if self.completable_milestones:
            lines.append(
                f"{len(self.completable_milestones)} milestone(s) with no open work order:"
            )
            for row in self.completable_milestones:
                lines.append(f"  {row['milestone_id'][:8]}  {_label(row['title'], 58)}")
                lines.append(f"      ds milestone close {row['milestone_id']}")
            lines.append("")
        if self.stale_in_progress:
            lines.append(
                f"{len(self.stale_in_progress)} work order(s) in_progress for over "
                f"{STALE_DAYS} days:"
            )
            for row in self.stale_in_progress:
                lines.append(
                    f"  {row['work_order_id'][:8]}  started {row['started_at'][:10]}  "
                    f"{_label(row['title'], 44)}"
                )
            lines.append("")
        lines.append(
            "Nothing above was changed. Closing runs the gates — independent review, "
            "executable ACs, the structural invariants — and a reconciler that closed "
            "these for you would bypass all of them on exactly the work nobody has "
            "looked at recently."
        )
        return "\n".join(lines)


def _label(value: str | None, width: int) -> str:
    """A row's title, trimmed — or a marker when the column is NULL.

    Found by running this against the live authority, not by imagining inputs: several
    work_order rows carry a NULL title. They are projection orphans — rows materialised
    from an event whose project no longer exists — and a reconciler that crashed on them
    would be unusable precisely where the data is worst. Printing an empty string would be
    worse still: it hides the one property that identifies them.
    """
    if value is None:
        return "(no title — projection orphan, see WO ff7c6ccc)"
    return value[:width]


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    except sqlite3.Error:
        return []


def find_drift(*, db_path: Path, project_id: str | None = None, now: str | None = None) -> Drift:
    """Records the authority holds open whose work appears finished.

    A work order counts as completable only when it HAS tasks and none remain open. A work
    order with zero tasks is not finished -- it is unstarted, and reporting it as closable
    would turn "nobody has written the tasks yet" into "ready to close", which is the
    absent-is-not-clean error this repository keeps finding.

    A milestone counts when it has no open work order. Unlike the structural invariant,
    which counts every sibling, here open-only is the right question: the milestone's
    remaining work is what decides whether it can close.
    """
    from datetime import UTC, datetime, timedelta

    drift = Drift()
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return drift

    scope = " AND w.project_id = ?" if project_id else ""
    params: tuple = (project_id,) if project_id else ()

    try:
        drift.completable_work_orders = _rows(
            conn,
            "SELECT w.work_order_id, w.title, w.status FROM business_work_orders w"
            f" WHERE w.status IN {_OPEN_WO}{scope}"
            "   AND EXISTS (SELECT 1 FROM business_tasks t"
            "               WHERE t.work_order_id = w.work_order_id)"
            "   AND NOT EXISTS (SELECT 1 FROM business_tasks t"
            "                   WHERE t.work_order_id = w.work_order_id"
            f"                     AND t.status NOT IN {_DONE_TASK})"
            " ORDER BY w.created_at",
            params,
        )

        ms_scope = " AND m.project_id = ?" if project_id else ""
        drift.completable_milestones = _rows(
            conn,
            "SELECT m.milestone_id, m.title, m.status FROM business_milestones m"
            " WHERE m.status NOT IN ('closed', 'cancelled', 'complete')"
            f"{ms_scope}"
            "   AND NOT EXISTS (SELECT 1 FROM business_work_orders w"
            "                   WHERE w.milestone_id = m.milestone_id"
            f"                     AND w.status IN {_OPEN_WO})"
            " ORDER BY m.order_index IS NULL, m.order_index, m.created_at",
            (project_id,) if project_id else (),
        )

        cutoff = (datetime.fromisoformat(now) if now else datetime.now(UTC)) - timedelta(
            days=STALE_DAYS
        )
        drift.stale_in_progress = _rows(
            conn,
            "SELECT w.work_order_id, w.title, w.started_at FROM business_work_orders w"
            " WHERE w.status = 'in_progress' AND w.started_at IS NOT NULL"
            f"   AND w.started_at < ?{scope}"
            " ORDER BY w.started_at",
            (cutoff.isoformat(),) + params,
        )
    finally:
        conn.close()

    return drift
