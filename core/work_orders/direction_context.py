"""Where the work is HEADED, not only where it is (WO-MULTIROOT-REVIEW task 9).

Operator: "the reviewer should be reviewing the code it is building or attempting to push
and take into account all relevant or connected pieces. whether that is multiple repos of
relevance or multiple milestones or work order for where we are headed and not where we
are at."

A grader sees one diff and one task list. Two of its judgements are not decidable from
that alone:

* "is this concise" — a mechanism that looks over-built for one work order is often the
  shared piece two siblings need. Judged on the snapshot, correct groundwork reads as
  gold-plating.
* "does it address the issue" — the issue is frequently the MILESTONE's, not the work
  order's. A work order that correctly does its slice can look like it missed the point.

So the grader is given the milestone this work order belongs to, its open siblings, and
its declared dependency edges. Not to widen its remit — the diff under review is still the
diff under review — but so those two judgements have their referent.

BOUNDED, AND THE TRUNCATION IS REPORTED. A project with sixty open work orders in one
milestone would otherwise push the diff out of the prompt, which is how WO-FALSIFY-TIMEOUT
started. The budget is characters, siblings are ordered so the most relevant survive
truncation, and what was dropped is stated rather than silently elided — an unmarked
partial list reads as a complete one.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

# Sized against the same pressure that produced the boundary-end fix: a work order whose
# evidence reached 217,524 chars timed the grader out at 360s. Direction context is
# supporting material, so it gets a small fraction of that.
_MAX_CHARS = 4_000
_MAX_SIBLINGS = 12

_OPEN = ("created", "in_progress")


def _rows(conn: sqlite3.Connection, sql: str, args: tuple[Any, ...]) -> list[tuple[Any, ...]]:
    try:
        return conn.execute(sql, args).fetchall()
    except sqlite3.Error:
        return []


def build_direction_context(
    work_order_id: str,
    *,
    db_path: Path,
) -> tuple[str, str | None]:
    """Return ``(context_text, truncation_note)`` for the grader prompt.

    ``context_text`` is empty when there is genuinely nothing to say — a work order with
    no milestone, no siblings, and no declared edges. Empty is honest there; the caller
    renders a line saying so rather than an empty section, because a blank block reads as
    "no direction" instead of "nothing recorded".
    """
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return "", "direction context unavailable: the authority could not be opened"

    try:
        wo = _rows(
            conn,
            "SELECT project_id, milestone_id, title FROM business_work_orders"
            " WHERE work_order_id = ?",
            (work_order_id,),
        )
        if not wo:
            return "", "direction context unavailable: work order not found"
        project_id, milestone_id, _title = wo[0]

        sections: list[str] = []
        dropped: list[str] = []

        # ── the milestone this work order serves ──────────────────────────────
        if milestone_id:
            ms = _rows(
                conn,
                "SELECT title, description, status FROM business_milestones"
                " WHERE milestone_id = ?",
                (milestone_id,),
            )
            if ms:
                m_title, m_desc, m_status = ms[0]
                desc = " ".join(str(m_desc or "").split())[:600]
                sections.append(
                    f"MILESTONE THIS WORK ORDER SERVES ({m_status}): {m_title}"
                    + (f"\n  {desc}" if desc else "")
                )
        else:
            sections.append(
                "MILESTONE: none recorded for this work order. Judge it on its own "
                "stated scope; there is no larger goal on record to judge it against."
            )

        # ── open siblings in the same milestone ───────────────────────────────
        # Ordered in_progress first, then by sequence: if the list is truncated, the work
        # actually underway is what survives, because that is what this diff most likely
        # has to interoperate with.
        siblings = _rows(
            conn,
            "SELECT work_order_id, title, status, work_order_type FROM business_work_orders"
            " WHERE milestone_id IS ? AND work_order_id != ?"
            f" AND status IN ({','.join('?' * len(_OPEN))})"
            " ORDER BY CASE status WHEN 'in_progress' THEN 0 ELSE 1 END,"
            "          sequence_order IS NULL, sequence_order, created_at",
            (milestone_id, work_order_id, *_OPEN),
        )
        if siblings:
            shown = siblings[:_MAX_SIBLINGS]
            lines = [f"  [{s[2]}] {s[1]} ({s[3] or 'untyped'}) — {s[0][:8]}" for s in shown]
            sections.append(
                "OPEN SIBLING WORK ORDERS IN THIS MILESTONE — a mechanism that looks "
                "over-built for this work order alone may be the shared piece one of "
                "these needs:\n" + "\n".join(lines)
            )
            if len(siblings) > len(shown):
                dropped.append(f"{len(siblings) - len(shown)} further open sibling(s) not listed")

        # ── declared dependency edges, both directions ────────────────────────
        blocking = _rows(
            conn,
            "SELECT w.work_order_id, w.title, w.status FROM work_order_dependencies d"
            " JOIN business_work_orders w ON w.work_order_id = d.depends_on_id"
            " WHERE d.work_order_id = ?",
            (work_order_id,),
        )
        blocked = _rows(
            conn,
            "SELECT w.work_order_id, w.title, w.status FROM work_order_dependencies d"
            " JOIN business_work_orders w ON w.work_order_id = d.work_order_id"
            " WHERE d.depends_on_id = ?",
            (work_order_id,),
        )
        if blocking:
            sections.append(
                "THIS WORK ORDER DEPENDS ON:\n"
                + "\n".join(f"  [{b[2]}] {b[1]} — {b[0][:8]}" for b in blocking)
            )
        if blocked:
            sections.append(
                "WORK ORDERS THAT DEPEND ON THIS ONE — groundwork they need is in scope "
                "here, not gold-plating:\n"
                + "\n".join(f"  [{b[2]}] {b[1]} — {b[0][:8]}" for b in blocked)
            )
        if not blocking and not blocked:
            sections.append(
                "DECLARED DEPENDENCIES: none. Independence is NOT verified — most work "
                "orders declare no edges, so absence here is silence, not proof."
            )

        text = "\n\n".join(sections)
        if len(text) > _MAX_CHARS:
            text = text[:_MAX_CHARS].rstrip()
            dropped.append(
                f"direction context truncated at {_MAX_CHARS} chars — this is a PARTIAL "
                "view of the surrounding work"
            )

        return text, ("; ".join(dropped) if dropped else None)
    finally:
        conn.close()
