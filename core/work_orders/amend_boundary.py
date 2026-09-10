"""Correct a work order's module boundary, recording what it was and why.

WO 9476516d. A boundary is composed into the description at CREATE time by
`compose_module_boundary`, and there was no way to change it afterwards -- the work-order
subcommands offer `set-order`, `add-dep` and `repoint-ac`, and nothing for the boundary. So
a work order whose scope legitimately grew could not have its boundary corrected, and the
admission Surveyor lane then refused tasks that genuinely belonged to it.

FOUND BY THE SUBSTRATE REFUSING ITS OWN AUTHOR, THREE TIMES on 2026-09-10: a task to retier
a gate against WO 17466550, a task to ship the registry against WO 09118a8e, and a third
against this milestone's own work. Every refusal was CORRECT -- the named file really was
outside the declared scope -- and the boundary was authored before the work order's shape
was known. The only ways out were to widen a boundary (no mechanism), file the task
somewhere it did not belong, or delete the path from the description to dodge the check.

THE DODGE IS THE REASON THIS EXISTS. `paths_named` judges only paths a description NAMES,
so the cheapest way past a correct refusal is a vaguer description -- which trades an
honest refusal for a silent misattribution. A boundary that can be corrected removes the
incentive.

DELIBERATELY SHAPED LIKE `repoint_ac`, which solved the same problem for an acceptance
criterion: a reason long enough to tell a typo from a moved goalpost, the prior value
recorded, and -- the load-bearing part -- the new value VALIDATED so the mechanism cannot
become a way to point at nothing. There, a criterion may only be repointed to a check that
can be found and run. Here, a boundary may only be amended to paths that EXIST, because
otherwise "widen it until the task is admitted" is one command away and the escape hatch
becomes the norm.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: Long enough to distinguish a correction from a widening. Same bar as `repoint_ac`.
_MIN_REASON = 30


def _strip_clause(description: str) -> str:
    """The description with its `Module boundary:` clause removed.

    `compose_module_boundary` deliberately leaves an existing clause alone -- "a caller who
    wrote it by hand is not second-guessed" -- so composing over one would append a second
    and the parser would keep reading the first. Amending means replacing, which means
    removing the old clause before composing the new one.
    """
    text = description or ""
    marker = "Module boundary:"
    start = text.find(marker)
    if start < 0:
        return text.rstrip()
    # The clause runs to the end of its sentence; `boundary_globs` reads to the first "."
    # that is not part of a path segment, so the same shape is removed here.
    tail = text[start + len(marker) :]  # noqa: E203
    end = len(tail)
    for index, char in enumerate(tail):
        if char == "\n":
            end = index
            break
        if char == "." and (index + 1 >= len(tail) or tail[index + 1] in " \n"):
            end = index + 1
            break
    return (text[:start] + tail[end:]).rstrip()


def amend_module_boundary(
    *,
    work_order_id: str,
    module_boundary: str,
    reason: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Replace a work order's boundary, recording the prior clause and why it moved."""
    from .mutations import compose_module_boundary
    from .start_shared import _require_db

    text = (reason or "").strip()
    if len(text) < _MIN_REASON:
        return {
            "ok": False,
            "error": (
                "Amending a boundary needs a reason a later reader can weigh — enough to"
                f" tell a correction from a widening ({_MIN_REASON}+ characters). A"
                " boundary quietly widened to admit a refused task is the escape hatch"
                " becoming the norm, which is what this records against."
            ),
        }

    declared = (module_boundary or "").strip()
    if not declared:
        return {"ok": False, "error": "No module boundary given."}

    db_path = _require_db(source_root, dream_studio_home)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT work_order_id, project_id, title, description"
            " FROM business_work_orders WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return {"ok": False, "error": f"Work order not found: {work_order_id}"}

    from runtime.lib.enforcement import boundary_globs

    previous_description = row["description"] or ""
    previous = boundary_globs(previous_description)

    parts = [p.strip().rstrip(".").strip() for p in declared.split(",")]
    parts = [p for p in parts if p]

    # VALIDATED, LIKE `repoint_ac` VALIDATES A CRITERION RESOLVES. A boundary naming paths
    # that do not exist would let anyone widen scope to admit whatever was refused, which
    # is exactly the dodge this command exists to remove.
    root = Path(source_root)
    missing = [p for p in parts if not (root / p).exists()]
    if missing:
        return {
            "ok": False,
            "error": (
                f"Refused — these paths do not exist: {', '.join(missing)}. A boundary may"
                " only name files or directories that are actually here; otherwise this"
                " becomes a way to widen scope until a refused task is admitted. Create the"
                " path first, or name the directory that will contain it."
            ),
        }

    usable = [p for p in parts if "/" in p or "." in p]
    if not usable:
        return {
            "ok": False,
            "error": (
                "Nothing here the boundary parser would keep — it retains only"
                " comma-separated parts containing '/' or '.'. Storing an unparseable"
                " boundary would look declared and match nothing, which is the failure"
                " `compose_module_boundary` exists to end."
            ),
        }

    if sorted(previous) == sorted(usable):
        return {"ok": False, "error": "That is already the boundary; nothing to amend."}

    rebuilt = compose_module_boundary(_strip_clause(previous_description), usable)
    now = datetime.now(UTC).isoformat()

    emitted = False
    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        _spool_writer.write_event(
            CanonicalEventEnvelope(
                event_type="work_order.boundary_amended",
                session_id=None,
                payload={
                    "module_boundary": usable,
                    "previous": previous,
                    "reason": text,
                    "description": rebuilt,
                },
                timestamp=now,
                severity="info",
                trace={
                    "domain": "sdlc",
                    "project_id": row["project_id"],
                    "work_order_id": work_order_id,
                    "attribution_status": "fully_attributed",
                },
            ).to_dict()
        )
        emitted = True
    except Exception as exc:  # noqa: BLE001 - the amendment is recorded either way
        emitted = False
        _emit_error = f"{type(exc).__name__}: {exc}"
    else:
        _emit_error = ""

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "UPDATE business_work_orders SET description = ?, updated_at = ?"
            " WHERE work_order_id = ?",
            (rebuilt, now, work_order_id),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "ok": True,
        "work_order_id": work_order_id,
        "module_boundary": usable,
        "previous": previous,
        "reason": text,
        # SAID OUT LOUD when the event did not land: the row is then rebuild-fragile, which
        # is WO 17466550's class, and a caller reading `ok: true` should know which.
        "event_emitted": emitted,
        **({"event_error": _emit_error} if not emitted else {}),
    }
