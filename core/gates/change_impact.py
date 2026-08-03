"""Change-impact affirmation gate — the Code History & Impact Guardrail, enforced.

CLAUDE.md's "Code History And Impact Guardrail" asks every change to be weighed against
its blast radius. R5 turns that from prose into a close-time record: before a work order
closes it must carry an **impact affirmation** — an explicit statement of which impact
classes the change touches (auth, contract, migration) and whether it is changelog-worthy.

The affirmation is stored in the authority as a WO artifact (kind ``impact_affirmation``)
via ``affirm_change_impact``; the ``change_impact_affirmed`` universal close gate
(core/work_orders/close_main.py) requires it. Work orders created before the cutover are
grandfathered — the guardrail is prospective, not retroactive.
"""

from __future__ import annotations

from typing import Any

# The impact classes, from CLAUDE.md's Code History & Impact Guardrail. An affirmation
# names which of these the change touches (an empty set is a valid, explicit "none").
IMPACT_CLASSES: tuple[str, ...] = ("auth", "contract", "migration", "changelog")

# Enforced only for work orders created on or after this date (the date the gate
# shipped). Earlier WOs are grandfathered. ISO date; compared against ISO created_at.
IMPACT_AFFIRM_ENFORCED_AFTER = "2026-08-02"

ARTIFACT_KIND = "impact_affirmation"


def render_affirmation(touched: object = (), note: str = "") -> str:
    """Render the affirmation artifact: a checkbox per impact class + an optional note.

    ``touched`` is the set of impact classes the change affects; unknown names are
    ignored so the record only ever reflects the canonical IMPACT_CLASSES.
    """
    touched_set = {str(t).lower() for t in touched}
    lines = ["# Change-Impact Affirmation", ""]
    for cls in IMPACT_CLASSES:
        mark = "x" if cls in touched_set else " "
        lines.append(f"- [{mark}] {cls}")
    if note.strip():
        lines += ["", f"Note: {note.strip()}"]
    return "\n".join(lines) + "\n"


def affirm_change_impact(
    work_order_id: str,
    *,
    touched: object = (),
    note: str = "",
    db_path: Any = None,
) -> bool:
    """Record an impact affirmation for a work order in the authority. Returns True on
    success (False if the artifact table is absent — same contract as set_wo_artifact)."""
    from core.work_orders.artifacts import set_wo_artifact

    return set_wo_artifact(
        work_order_id, ARTIFACT_KIND, render_affirmation(touched, note), db_path=db_path
    )


def _wo_created_at(conn: Any, work_order_id: str) -> str | None:
    try:
        row = conn.execute(
            "SELECT created_at FROM business_work_orders WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
    except Exception:
        return None
    return row[0] if row else None


def _is_grandfathered(created_at: str | None, enforced_after: str) -> bool:
    # No known creation time, or created before the cutover → exempt.
    return not created_at or created_at[:10] < enforced_after


def check_change_impact_affirmed(
    conn: Any,
    work_order_id: str,
    db_path: Any = None,
    *,
    enforced_after: str = IMPACT_AFFIRM_ENFORCED_AFTER,
) -> list[str]:
    """Return [] if the WO is grandfathered or carries an impact affirmation; otherwise
    a one-element list with the failure reason. Universal close gate — WO-type agnostic."""
    if _is_grandfathered(_wo_created_at(conn, work_order_id), enforced_after):
        return []
    from core.work_orders.artifacts import get_wo_artifact

    if get_wo_artifact(work_order_id, ARTIFACT_KIND, db_path=db_path) is None:
        return [
            "change_impact_affirmed: no impact affirmation recorded — run "
            "`ds work-order affirm-impact <id>` to affirm the change's impact classes "
            "(auth/contract/migration/changelog; see CLAUDE.md Code History & Impact Guardrail)"
        ]
    return []
