"""Gap generation, dedup, and gap-work-order insertion for work-order verify.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/verify.py``. Holds the
grader-output-to-gap conversion helpers, the invented-threshold filter, the
stable gap-key/category dedup machinery, and the authority INSERT of spawned
gap work orders/tasks. No logic changes — extracted verbatim from the
original module.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

# ── Gap generation helpers ──────────────────────────────────────────────────────


def normalise_falsification_scenarios(payload: Any) -> tuple[list[dict[str, Any]], int]:
    """Coerce a falsification grader's ``scenarios`` into ``(well_formed, malformed_count)``.

    ONE shared normaliser because the payload has TWO readers, and the first fix
    hardened only one of them (gap WO 66e7ebc8): ``_falsification_to_gaps`` was
    guarded while ``verify_main``'s ``_unverified`` comprehension still called
    ``.get()`` on every element, so the very reply the WO was about still raised
    AttributeError inside verify's OPEN authority transaction. Two copies of a
    shape contract is how one of them stays wrong.

    A live grader can return prose (``["crash mid write is untested"]``), a bare
    scenario object instead of a list, or another command's JSON entirely. Non-dict
    entries are skipped and COUNTED — the count is reported downstream, because
    silently dropping unparseable entries makes a narrowed enumeration
    indistinguishable from a complete one.
    """
    if isinstance(payload, dict):  # a single scenario object, not a list
        payload = [payload]
    elif not isinstance(payload, list):
        return [], 0
    well_formed = [s for s in payload if isinstance(s, dict)]
    return well_formed, len(payload) - len(well_formed)


def _falsification_to_gaps(scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Error-severity PROPOSED scenarios → one gap WO carrying the missing tests.

    WO-FALSIFY-FIRST-PASS. Only PROPOSED-and-error scenarios spawn: the analyst
    has said the worst-case IS testable and no test exists, which is exactly
    actionable work. COVERED needs nothing; UNVERIFIED has nothing to write yet
    and is recorded in the unverified-risks ledger instead (named, not silent).
    The gap category is stable (``missing-adversarial-tests``) so re-verifies
    dedup against the same spawn rather than breeding duplicates.

    Shape-tolerant via the shared normaliser above — see its docstring for why
    that is shared rather than inlined here.
    """
    well_formed, malformed_count = normalise_falsification_scenarios(scenarios)
    actionable = [
        s for s in well_formed if s.get("status") == "PROPOSED" and s.get("severity") == "error"
    ]
    if not actionable:
        return []
    tasks = [
        {
            "title": (
                f"Add adversarial test: {s.get('scenario_class', 'unknown')} on "
                f"{s.get('surface', 'unknown surface')}"
            ),
            "description": (
                f"Worst case: {s.get('scenario', '')}\n" f"Proposed test: {s.get('evidence', '')}"
            ),
        }
        for s in actionable
    ]
    return [
        {
            "title": "Add missing adversarial tests for durable/reachable failure modes",
            "description": (
                f"{len(actionable)} error-severity worst-case scenario(s) are testable but "
                "untested (falsification analyst). See review-verdict.json "
                "falsification.scenarios for the full enumeration.\n"
                + (
                    f"NOTE: {malformed_count} scenario entr(ies) were malformed (not objects) "
                    "and could not be classified — the enumeration may be incomplete.\n"
                    if malformed_count
                    else ""
                )
                + "[gap-category: missing-adversarial-tests]"
            ),
            "work_order_type": "cleanup",
            "tasks": tasks,
        }
    ]


# A grader reports "I could not judge this" through these values. None of them locate a
# defect, and a finding that cannot be located cannot be fixed.
_UNLOCATABLE = frozenset({"", "n/a", "na", "none", "null", "unknown", "-"})


def _violation_is_locatable(violation: dict[str, Any]) -> bool:
    """Does this violation name something a person could go and fix?

    Requires a real rule OR a real file. Both blank/"N/A" means the grader is reporting
    its own inability, not a defect in the work — see the note in ``_violations_to_gaps``.
    """
    rule = str(violation.get("rule") or "").strip().lower()
    file = str(violation.get("file") or "").strip().lower()
    return rule not in _UNLOCATABLE or file not in _UNLOCATABLE


def _violations_to_gaps(
    violations: list[dict[str, Any]],
    coverage_gaps: list[dict[str, Any]],
    migration_gaps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    # AN UNREVIEWABLE FINDING IS NOT WORK. Measured: the correctness grader reported
    # "independent review unverifiable — no diff provided" because it could not reach the
    # target repo, and the spawner turned that into work order 58e21003 with the task
    # "Fix N/A: independent review unverifiable — no diff provided in N/A". The
    # reviewer's INABILITY to review was laundered into scheduled work.
    #
    # A violation with no locatable target — no rule, no file, or the literal "N/A" —
    # is the grader saying it could not judge. It belongs on the verdict, not in the
    # queue. A violation that names a real rule or file is untouched.
    violations = [v for v in violations if _violation_is_locatable(v)]
    if violations:
        tasks = [
            {
                "title": f"Fix {v.get('rule', 'violation')} in {v.get('file', 'unknown')}",
                "description": v.get("detail", ""),
            }
            for v in violations
        ]
        gaps.append(
            {
                "title": "Fix architectural violations flagged by correctness grader",
                "description": (
                    f"{len(violations)} architectural rule violation(s) detected in diff. "
                    "See review-verdict.json correctness.violations for details."
                ),
                "work_order_type": "cleanup",
                "tasks": tasks,
            }
        )
    if coverage_gaps:
        tasks = [
            {
                "title": (
                    f"Add tests for {g.get('function', g.get('fn', 'function'))} "
                    f"in {g.get('file', 'unknown')}"
                ),
                "description": "No test coverage found for this function/command.",
            }
            for g in coverage_gaps
        ]
        gaps.append(
            {
                "title": "Add missing test coverage",
                "description": (
                    f"{len(coverage_gaps)} public function(s) or command(s) lack test coverage."
                ),
                "work_order_type": "infrastructure",
                "tasks": tasks,
            }
        )
    if migration_gaps:
        tasks = [
            {"title": g.get("item", "Fix migration gap"), "description": ""} for g in migration_gaps
        ]
        gaps.append(
            {
                "title": "Fix migration hygiene issues",
                "description": (
                    f"{len(migration_gaps)} migration hygiene issue(s) found. "
                    "See review-verdict.json correctness.migration_gaps."
                ),
                "work_order_type": "infrastructure",
                "tasks": tasks,
            }
        )
    return gaps


def _quality_issues_to_gaps(error_issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not error_issues:
        return []
    tasks = [
        {
            "title": (f"Fix {i.get('category', 'quality')} issue in {i.get('file', 'unknown')}"),
            "description": i.get("detail", ""),
        }
        for i in error_issues
    ]
    return [
        {
            "title": "Fix error-severity quality issues",
            "description": (
                f"{len(error_issues)} error-severity quality issue(s) detected. "
                "See review-verdict.json quality.issues."
            ),
            "work_order_type": "cleanup",
            "tasks": tasks,
        }
    ]


def _migration_risks_to_gaps(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    error_risks = [r for r in risks if r.get("severity") == "error"]
    if not error_risks:
        return []
    tasks = [
        {
            "title": f"Resolve {r.get('category', 'migration')} risk",
            "description": r.get("detail", ""),
        }
        for r in error_risks
    ]
    return [
        {
            "title": "Resolve migration safety risks",
            "description": (
                f"{len(error_risks)} error-severity migration risk(s) found. "
                "See review-verdict.json migration.risks."
            ),
            "work_order_type": "infrastructure",
            "tasks": tasks,
        }
    ]


# ── Gap WO insertion ────────────────────────────────────────────────────────────


# WO-SPAWN-LOOP-FIX: regex for numeric thresholds (line counts, coverage %, etc.)
# that a grader might fabricate. Used to reject gaps that invent a threshold absent
# from the explicit acceptance-criteria text.
_THRESHOLD_RE = re.compile(
    r"(?:<=|>=|<|>|≤|≥|under|below|at most|no more than|at least|over)?\s*\d+\s*"
    r"(?:lines?|%|percent|chars?|characters?|tokens?|loc)\b",
    re.IGNORECASE,
)


def _gap_category(gap: dict[str, Any]) -> str:
    """Return a stable category for a gap, independent of free-text phrasing.

    Prefers an explicit ``category`` field emitted by the grader. Falls back to a
    normalized form of the title (lowercased, alphanumerics only) so legacy gaps
    without a category still dedup against an identical title. Rephrased titles
    only dedup when the grader supplies a stable ``category`` (WO-SPAWN-LOOP-FIX T1).
    """
    explicit = (gap.get("category") or "").strip().lower()
    if explicit:
        return re.sub(r"[^a-z0-9]+", "-", explicit).strip("-")
    title = (gap.get("title") or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", title).strip("-")


# WO-GAP-DEDUPE-CLASS: generic advisory gap categories that are the SAME finding
# on any work order (they do not describe a specific WO's content). These dedup
# project-wide by category alone, so the class spawns at most one open tracking WO
# instead of a near-duplicate per reviewed WO. Content-specific categories
# (missing-tests, task-N-incomplete, …) stay scoped to the reviewed WO.
_ADVISORY_PROJECT_WIDE_CATEGORIES = frozenset(
    {
        "missing-behavioral-ac",
        # MEASURED 2026-08-21 on the live authority. These two classes produced 19 of
        # the 25 auto-spawned work orders since 08-19 — x11 and x8 — each with a
        # DISTINCT gap key differing only in the reviewed-WO id before the "::".
        # Verify created 118 work orders and closed 43 over three days; this is where
        # most of the difference came from.
        "add-missing-adversarial-tests-for-durable-reachable-failure-modes",
        "add-missing-test-coverage",
    }
)

# How many open spawns of one category, across DIFFERENT reviewed work orders, before
# the class is treated as project-wide regardless of the allowlist above.
#
# The allowlist alone cannot hold: it enumerates the grader's canned phrasings, and a
# rephrasing produces a new category that fans out again — which is exactly what
# happened after WO-GAP-DEDUPE-CLASS added the first entry and two later phrasings
# sailed past it. At 2, an unrecognised class spawns at most twice before it
# self-corrects, whatever it is called next.
_PROJECT_WIDE_AFTER_N_OPEN_SPAWNS = 2


def _category_open_spawn_count(conn: Any, project_id: str, category: str) -> int:
    """Open spawned WOs for this category across DIFFERENT reviewed work orders.

    Counts by the category half of the ``[gap-key: <reviewed>::<category>]`` marker, so
    it answers "has this class already fanned out" without needing to know which
    reviewed WOs produced it. Failure to query returns 0 — a backstop that raises would
    break verify, and losing the backstop is a smaller harm than that.
    """
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM business_work_orders"
            " WHERE project_id = ? AND status IN ('created', 'in_progress')"
            "   AND instr(description, ?) > 0",
            (project_id, f"::{category}]"),
        ).fetchone()
    except Exception:  # noqa: BLE001 - a dedup backstop must never break a verify
        return 0
    return int(row[0]) if row and row[0] is not None else 0


def _gap_key(
    reviewed_work_order_id: str,
    gap: dict[str, Any],
    *,
    conn: Any = None,
    project_id: str | None = None,
) -> str:
    """Stable dedup key for a spawned gap.

    Normally (reviewed WO id + gap category), stored as a ``[gap-key: ...]`` marker
    on the spawned WO's description so later re-reviews recognize prior spawns
    regardless of title phrasing (T1). For generic advisory categories
    (``_ADVISORY_PROJECT_WIDE_CATEGORIES``) the reviewed-WO id is dropped so the
    class dedups project-wide — otherwise the same advisory finding respawns a
    near-duplicate WO on every reviewed WO (WO-GAP-DEDUPE-CLASS).

    WO-GAP-FANOUT adds the backstop the allowlist needed. Given ``conn`` and
    ``project_id``, a category that ALREADY has
    ``_PROJECT_WIDE_AFTER_N_OPEN_SPAWNS`` open spawns across different reviewed work
    orders becomes project-wide even when it is not on the list. Measured cause: the
    list held one entry while two unlisted classes produced 19 of 25 spawns in three
    days, each with its own reviewed-WO-scoped key.

    A CONTENT-SPECIFIC GAP STAYS SCOPED, and that is the point of the original design:
    "task 3 was never implemented" is about ONE work order and must not dedup against
    another's. The backstop only fires on a class that has demonstrably repeated, so a
    genuine per-WO finding is never merged away on its first or second appearance.
    """
    category = _gap_category(gap)
    if category in _ADVISORY_PROJECT_WIDE_CATEGORIES:
        return f"advisory::{category}"
    if conn is not None and project_id:
        if (
            _category_open_spawn_count(conn, project_id, category)
            >= _PROJECT_WIDE_AFTER_N_OPEN_SPAWNS
        ):
            return f"advisory::{category}"
    return f"{reviewed_work_order_id}::{category}"


def _gap_key_marker(gap_key: str) -> str:
    return f"[gap-key: {gap_key}]"


# How many distinct gap rounds a work order may absorb before the attach loop is called
# out. Chosen to bound, not to block: attaching keeps working past this, but silence does
# not. A bound nobody can see is the same defect as no bound.
_ATTACH_ROUNDS_BEFORE_PRESSURE = 3

# Written with an explicit newline escape in a named constant: an inline f-string with
# escaped newlines was mangled twice by shell quoting while this module was authored.
_GAP_ATTACHED_STAMP = "\n\n[gap-attached: {gap_key}]"


def _attached_gap_keys(conn: Any, work_order_id: str) -> set[str]:
    """Distinct gap keys already attached to this work order as tasks."""
    marker = "[gap-attached: "
    try:
        rows = conn.execute(
            "SELECT description FROM business_tasks WHERE work_order_id = ?", (work_order_id,)
        ).fetchall()
    except Exception:  # noqa: BLE001 - counting must never break a verify
        return set()
    keys: set[str] = set()
    for (desc,) in rows:
        text = desc or ""
        start = text.find(marker)
        if start >= 0:
            # Bound the key with named indices rather than an expression inside the
            # slice: black formats `text[a + b : c]` with spaces around the colon, which
            # flake8 reports as E203, and the two tools cannot both be satisfied inline.
            begin = start + len(marker)
            end = text.find("]", begin)
            if end > begin:
                keys.add(text[begin:end])
    return keys


def _attach_gap_tasks(
    conn: Any,
    *,
    work_order_id: str,
    project_id: str,
    tasks: list[dict[str, Any]],
    now: str,
    gap_key: str = "",
) -> int:
    """Add a gap's tasks to an existing work order. Returns how many were added.

    Skips a task whose title is already on that work order, so re-reviewing does not
    accumulate duplicates of the same finding — the per-work-order equivalent of the
    gap-key dedup one level up.
    """
    try:
        existing = {
            (r[0] or "").strip().lower()
            for r in conn.execute(
                "SELECT title FROM business_tasks WHERE work_order_id = ?", (work_order_id,)
            ).fetchall()
        }
    except Exception:  # noqa: BLE001 - never break a verify over dedup bookkeeping
        existing = set()

    added = 0
    for task in tasks:
        title = str(task.get("title", "") or "")
        if title.strip().lower() in existing:
            continue
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, description,"
            "  status, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
            (
                str(uuid.uuid4()),
                work_order_id,
                project_id,
                title,
                # The key rides the task so repeated attachment rounds are countable —
                # title dedup stops the SAME finding repeating, but says nothing about a
                # NEW finding every round, which is the loop this bounds.
                (task.get("description", "") or "")
                + (_GAP_ATTACHED_STAMP.format(gap_key=gap_key) if gap_key else ""),
                now,
                now,
            ),
        )
        existing.add(title.strip().lower())
        added += 1
    return added


def _work_order_is_open(conn: Any, work_order_id: str) -> bool:
    """Is this work order still open, i.e. can a task be added to it?"""
    try:
        row = conn.execute(
            "SELECT status FROM business_work_orders WHERE work_order_id = ?", (work_order_id,)
        ).fetchone()
    except Exception:  # noqa: BLE001 - fall back to the spawning path rather than raise
        return False
    return bool(row) and row[0] in ("created", "in_progress")


def _filter_invented_threshold_gaps(
    gaps: list[dict[str, Any]], acceptance_text: str
) -> list[dict[str, Any]]:
    """Drop gaps that fabricate a numeric threshold absent from the AC text.

    A grader must only flag gaps against EXPLICIT acceptance criteria. If a gap's
    title/description/tasks introduce a numeric threshold (e.g. "<=50 lines",
    "90% coverage") that does not appear in *acceptance_text*, the gap is an
    invented threshold and is rejected (WO-SPAWN-LOOP-FIX T2).
    """
    ac_thresholds = {
        m.group(0).lower().replace(" ", "") for m in _THRESHOLD_RE.finditer(acceptance_text)
    }
    kept: list[dict[str, Any]] = []
    for gap in gaps:
        text_parts = [gap.get("title", ""), gap.get("description", "")]
        for task in gap.get("tasks", []):
            text_parts.append(task.get("title", ""))
            text_parts.append(task.get("description", ""))
        gap_text = " ".join(text_parts)
        gap_thresholds = {
            m.group(0).lower().replace(" ", "") for m in _THRESHOLD_RE.finditer(gap_text)
        }
        invented = gap_thresholds - ac_thresholds
        if invented:
            continue  # fabricated threshold not grounded in the AC — reject
        kept.append(gap)
    return kept


def _insert_gap_work_orders(
    conn: Any,
    *,
    gaps: list[dict[str, Any]],
    project_id: str,
    milestone_id: str | None,
    reviewed_work_order_id: str,
    reviewed_wo_title: str,
    reviewed_wo_sequence: int | None,
    reviewed_wo_incomplete: bool = False,
) -> list[dict[str, Any]]:
    now = datetime.now(UTC).isoformat()
    spawned: list[dict[str, Any]] = []

    base_seq = reviewed_wo_sequence or 0
    if milestone_id:
        max_seq_row = conn.execute(
            "SELECT MAX(sequence_order) FROM business_work_orders WHERE milestone_id = ?",
            (milestone_id,),
        ).fetchone()
        if max_seq_row and max_seq_row[0] is not None:
            base_seq = max(base_seq, max_seq_row[0])

    new_wo_counter = 0
    for gap in gaps:
        wo_type = gap.get("work_order_type", "cleanup")
        gap_title = gap["title"]
        gap_key = _gap_key(reviewed_work_order_id, gap, conn=conn, project_id=project_id)
        marker = _gap_key_marker(gap_key)

        # A PROJECT-WIDE key searches by the CATEGORY SUFFIX, not the whole marker, so
        # it merges into a prior scoped spawn of the same class instead of adding one
        # more beside it. Without this the class stabilised at THREE open work orders,
        # not two: at the moment the backstop flips, no `advisory::` marker exists yet,
        # so the lookup missed the two scoped siblings and minted a third. Measured by
        # the test, not reasoned about — it asserted 2 and got 3.
        #
        # It is also what drains the duplicates already in the queue: the next spawn of
        # a class that fanned out merges into one of them rather than extending the run.
        search_needle = f"::{_gap_category(gap)}]" if gap_key.startswith("advisory::") else marker

        # A GAP IN AN OPEN, INCOMPLETE WORK ORDER IS THAT WORK ORDER'S OWN UNFINISHED
        # WORK, so it becomes a TASK on it rather than a sibling (operator ruling,
        # 2026-08-26). Measured: of the 10 open reviewer spawns, five were findings
        # about the very work order under review. Spawning a sibling declares the
        # reviewed work order complete and re-homes its remainder — routing AROUND the
        # tasks_done gate that already refuses to close a work order with open tasks.
        #
        # TWO CONDITIONS, and the second was missing from the first cut. An existing
        # test caught it: a PASSING verify carrying a warning-severity gap would have
        # had blocking tasks attached to the work order it had just certified, so the
        # review's own approval could not be acted on. Attach only when the verdict says
        # the work is NOT done — that is what makes the gap "its own unfinished work"
        # rather than an advisory note about finished work.
        #
        # A closed reviewed work order also spawns a sibling: it has nowhere to put a
        # task.
        if reviewed_wo_incomplete and _work_order_is_open(conn, reviewed_work_order_id):
            prior_rounds = _attached_gap_keys(conn, reviewed_work_order_id)
            added = _attach_gap_tasks(
                conn,
                work_order_id=reviewed_work_order_id,
                project_id=project_id,
                tasks=gap.get("tasks", [])
                or [{"title": gap_title, "description": gap["description"]}],
                now=now,
                gap_key=gap_key,
            )
            record: dict[str, Any] = {
                "work_order_id": reviewed_work_order_id,
                "title": gap_title,
                "type": wo_type,
                "gap_key": gap_key,
                "attached_to_reviewed": True,
                "tasks_added": added,
            }
            # BOUND THE ATTACH LOOP, VISIBLY. Attaching makes a failing verdict block the
            # close through tasks_done, which is honest — the work order genuinely is not
            # done. But verify -> attach -> fix -> verify -> attach a NEW finding is the
            # original complaint ("something else always gets surfaced") wearing a
            # blocking face instead of an inflating one. Title dedup stops the SAME
            # finding repeating and says nothing about a new one each round.
            #
            # This does not stop attaching. It stops the growth being SILENT, and names
            # the honest exit: carry the remainder rather than let one work order absorb
            # an unbounded number of reviews.
            rounds = len(prior_rounds | {gap_key})
            if rounds >= _ATTACH_ROUNDS_BEFORE_PRESSURE:
                record["attachment_pressure"] = (
                    f"this work order has absorbed gaps on {rounds} separate reviews."
                    " Consider carrying the remainder into a new work order and closing"
                    " this one at its true scope, rather than letting one work order"
                    " grow without bound."
                )
            spawned.append(record)
            continue

        # Dedup on the stable gap key, NOT the free-text title, scoped by project_id
        # so null-milestone gaps still dedup (T3). Match across ANY status so a closed
        # prior spawn is never re-spawned (T4 respawn cap). Prefer an open WO so we can
        # merge tasks into it; a closed match means skip-and-log.
        existing_row = conn.execute(
            "SELECT work_order_id, status FROM business_work_orders"
            " WHERE project_id = ? AND instr(description, ?) > 0"
            " ORDER BY CASE status"
            "   WHEN 'in_progress' THEN 0 WHEN 'created' THEN 1 ELSE 2 END,"
            "   created_at ASC"
            " LIMIT 1",
            (project_id, search_needle),
        ).fetchone()

        if existing_row and existing_row[1] not in ("created", "in_progress"):
            # T4 respawn cap: a prior spawn for this gap key already exists (closed).
            # Never spawn it again — skip and record the suppression.
            spawned.append(
                {
                    "work_order_id": existing_row[0],
                    "title": gap_title,
                    "type": wo_type,
                    "gap_key": gap_key,
                    "respawn_suppressed": True,
                }
            )
            continue

        if existing_row:
            target_wo_id = existing_row[0]
            _attach_gap_tasks(
                conn,
                work_order_id=target_wo_id,
                project_id=project_id,
                tasks=gap.get("tasks", []),
                now=now,
            )
            spawned.append(
                {
                    "work_order_id": target_wo_id,
                    "title": gap_title,
                    "type": wo_type,
                    "gap_key": gap_key,
                    "merged_into_existing": True,
                }
            )
        else:
            new_wo_id = str(uuid.uuid4())
            seq = base_seq + new_wo_counter + 1
            new_wo_counter += 1
            desc = (
                f"Spawned by review of '{reviewed_wo_title}' on {now[:10]}: "
                f"{gap.get('description', '')} {marker}"
            )
            conn.execute(
                "INSERT INTO business_work_orders"
                " (work_order_id, project_id, milestone_id, title, description,"
                "  work_order_type, status, sequence_order, created_at, updated_at, last_updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, 'created', ?, ?, ?, ?)",
                (
                    new_wo_id,
                    project_id,
                    milestone_id,
                    gap_title,
                    desc,
                    wo_type,
                    seq,
                    now,
                    now,
                    now,
                ),
            )
            for task in gap.get("tasks", []):
                task_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO business_tasks"
                    " (task_id, work_order_id, project_id, title, description,"
                    "  status, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
                    (
                        task_id,
                        new_wo_id,
                        project_id,
                        task.get("title", ""),
                        task.get("description", ""),
                        now,
                        now,
                    ),
                )
            spawned.append(
                {
                    "work_order_id": new_wo_id,
                    "title": gap_title,
                    "type": wo_type,
                    "gap_key": gap_key,
                }
            )

    return spawned
