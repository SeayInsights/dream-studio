"""Event-sourced backfill: assign every unassigned project a client (Client Layer, Phase 2).

Classification (operator 2026-08-08): a project whose name OR path mentions "fulcrum" -> Fulcrum;
"hypershift" -> Hypershift; everything else -> SeayInsights (the default). Each assignment is a
project.client_assigned EVENT (attribution_status='backfill') applied by ProjectProjection — no
direct read-model write. Idempotent: only projects with client_id IS NULL are touched.

Wired into ``core.config.sqlite_bootstrap.activate_pending_migrations`` so activating migration 155
(``ds migrate activate``) classifies the existing projects. Fresh installs have no projects, so it
is a no-op there.

THE ROUND-TABLE BUG. The bare substring match above only ever sees ``business_projects.name`` and
``.project_path`` -- and a project registered from wherever a review happened to check code out
(a worktree of someone else's repository, taken under round-table's own working tree for a
one-off inspection) carries a path that names the REVIEWING TOOL's layout, not the client's
repository. ``round-table/_reviews/plat-roundtable`` has no "fulcrum" in it even when every commit
inside it is Fulcrum's platform repo, so the bare heuristic -- and the registration-time default it
backs, both falling through to the same ``_MATCH_RULES`` miss -- classify it SeayInsights.

``classify_project_for_work_order`` and ``reconcile_project_client_from_review`` close that gap
for exactly the callers that can: anything resolving a work order's project already has
``core.work_orders.project_roots.resolve_project_roots`` available (the same lookup
``core.work_orders.review_answers.dispatch_review_round`` uses for ``change_root``), which knows a
worktree from the repository it branches from. A standalone caller with no work order and no
resolvable root keeps the bare path-prefix heuristic exactly as before -- there is no better
signal to prefer there, and guessing one would be the silent-default failure this module exists to
avoid.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.work_orders.project_roots import ProjectRoots

_MATCH_RULES = (
    ("fulcrum", "fulcrum"),
    ("hypershift", "hypershift"),
)

#: The client every project lands on with no identifying signal at all
#: (`core.clients.queries.resolve_default_client`), and the one `detach_project_client`
#: resets a project TO rather than to NULL -- this module's own convention that
#: "SeayInsights" already means "not particularly attributed", not a researched fact
#: about whose work it is. `reconcile_project_client_from_review` treats a project
#: currently sitting on it (or on no client at all) as safe to upgrade when a better
#: signal disagrees, and never touches a project already carrying `fulcrum` or
#: `hypershift` -- an explicit or previously-resolved non-default assignment is never
#: silently overwritten.
_UNCLASSIFIED_SENTINEL = "seayinsights"


def classify_project(
    name: str | None, project_path: str | None, *, resolved_root: str | None = None
) -> str:
    """Return the client_id a project maps to by name-or-path (else the SeayInsights default).

    ``resolved_root`` -- the project's ACTUAL code root, once resolved -- takes priority over
    the bare ``project_path`` column when given, for exactly the reason this module's own
    docstring names: a review tool's scratch checkout is not a description of whose code it
    holds. Omitted (the default), this is unchanged from before `resolved_root` existed.
    """
    haystack = f"{name or ''} {resolved_root or project_path or ''}".lower()
    for client_id, term in _MATCH_RULES:
        if term in haystack:
            return client_id
    return "seayinsights"


def _resolve_db(db_path: Path | None) -> Path:
    if db_path is not None:
        return Path(db_path)
    from core.config.database import _default_db_path

    return _default_db_path()


def _resolved_root_for_classification(roots: "ProjectRoots") -> Path | None:
    """The one path that actually identifies whose code a resolved ``ProjectRoots`` holds.

    A WORKTREE NAMES A BRANCH OF ANOTHER REPOSITORY. ``resolve_project_roots`` keeps
    ``.primary`` pointed at a declared worktree itself -- correctly, that IS the code to grade
    -- but the worktree's own folder can live anywhere, including inside a review tool's own
    working tree while the repository it branches from lives wherever that client's code
    normally does. ``.checkouts`` already records that repository; this is the one case
    ``.primary`` alone does not cover, so it is special-cased here rather than in
    ``ProjectRoots`` itself, whose own contract (grade the worktree) is correct for grading
    and wrong for classification.

    Every other shape -- a single repository, or a container with exactly one nested
    repository -- is already what ``.primary`` returns, so this falls through to it.
    """
    if (
        len(roots.roots) == 1
        and len(roots.checkouts) == 1
        and roots.checkouts[0][0] == roots.roots[0]
    ):
        return roots.checkouts[0][1]
    return roots.primary


def _project_for_work_order(work_order_id: str, db: Path) -> sqlite3.Row | None:
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT p.project_id, p.name, p.project_path, p.client_id"
            " FROM business_work_orders w JOIN business_projects p ON w.project_id = p.project_id"
            " WHERE w.work_order_id = ?",
            (work_order_id,),
        ).fetchone()
    finally:
        conn.close()


def classify_project_for_work_order(
    work_order_id: str,
    *,
    db_path: Path | None = None,
    roots: "ProjectRoots | None" = None,
) -> str | None:
    """Classify a work order's project, keyed on the repo actually under review.

    Resolves the SAME roots ``core.work_orders.review_answers.dispatch_review_round`` calls
    ``change_root`` (pass an already-resolved ``roots`` to avoid recomputing it), unwraps a
    worktree to the repository it belongs to, and classifies against that instead of the bare
    ``business_projects.project_path`` column.

    Returns None when the work order names no project, or that project declares no
    ``project_path`` -- there is nothing to resolve, and the caller should fall back to the
    bare-path heuristic (``classify_project(name, project_path)``) rather than receive a
    guess.
    """
    db = _resolve_db(db_path)
    row = _project_for_work_order(work_order_id, db)
    if row is None or not row["project_path"]:
        return None

    if roots is None:
        from core.work_orders.project_roots import resolve_project_roots

        roots = resolve_project_roots(work_order_id, db)

    resolved = _resolved_root_for_classification(roots)
    return classify_project(
        row["name"], row["project_path"], resolved_root=str(resolved) if resolved else None
    )


def reconcile_project_client_from_review(
    work_order_id: str, roots: "ProjectRoots", *, db_path: Path | None = None
) -> dict[str, Any] | None:
    """Correct a work order's project client at the moment round-table resolves its real
    ``change_root`` -- the round-table bug, closed at the one live call site that has the
    signal to close it.

    NEVER OVERWRITES AN EXPLICIT OR ALREADY-RESOLVED NON-DEFAULT CLIENT. A project currently
    assigned ``fulcrum`` or ``hypershift`` is left exactly as it is, even when the resolved
    root disagrees -- this module has no queryable record of WHY a client was assigned
    (``attribution_status`` lives only in the event's trace, not a materialized column), so it
    can never tell a deliberate reassignment from a stale guess. Only a project sitting on no
    client, or on the SeayInsights default -- which this whole system already treats as "not
    particularly attributed" rather than a researched fact, see ``_UNCLASSIFIED_SENTINEL`` --
    is eligible to move, and only when the resolved signal actually disagrees with it.

    Returns the ``assign_project_client`` result when it reassigned something, None when there
    was nothing to resolve or nothing worth changing.
    """
    db = _resolve_db(db_path)
    row = _project_for_work_order(work_order_id, db)
    if row is None or not row["project_path"]:
        return None

    current = row["client_id"] or _UNCLASSIFIED_SENTINEL
    if current not in (_UNCLASSIFIED_SENTINEL,):
        return None

    resolved = classify_project_for_work_order(work_order_id, db_path=db, roots=roots)
    if resolved is None or resolved == current:
        return None

    from core.clients.mutations import assign_project_client

    return assign_project_client(
        project_id=row["project_id"], client_id=resolved, attribution_status="backfill"
    )


def backfill_project_clients(*, db_path: Path | None = None) -> dict[str, Any]:
    """Emit a project.client_assigned event for every project with client_id IS NULL, classified by
    name/path. Returns {ok, assigned: {client_id: count}}.

    PREFERS A RESOLVED WORK-ORDER ROOT OVER THE BARE PATH, where one exists. A project with a
    work order on record can be classified by ``classify_project_for_work_order`` -- the real
    repository under review, not the bare ``project_path`` column -- and this falls back to the
    plain ``classify_project(name, project_path)`` heuristic exactly as before whenever no work
    order names the project, or resolution finds nothing better.
    """
    from core.clients.mutations import assign_project_client

    db = _resolve_db(db_path)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT project_id, name, project_path FROM business_projects WHERE client_id IS NULL"
        ).fetchall()
        # Any one work order per project suffices: resolution keys off project_path, which is
        # the same regardless of which of a project's work orders names it.
        wo_by_project = dict(
            conn.execute(
                "SELECT project_id, MIN(work_order_id) FROM business_work_orders GROUP BY project_id"
            ).fetchall()
        )
    finally:
        conn.close()

    counts: dict[str, int] = {}
    for r in rows:
        work_order_id = wo_by_project.get(r["project_id"])
        client_id = (
            classify_project_for_work_order(work_order_id, db_path=db) if work_order_id else None
        )
        if client_id is None:
            client_id = classify_project(r["name"], r["project_path"])
        assign_project_client(
            project_id=r["project_id"], client_id=client_id, attribution_status="backfill"
        )
        counts[client_id] = counts.get(client_id, 0) + 1
    return {"ok": True, "assigned": counts}
