"""Shared logic for SQLite-usage enforcement hooks.

Used by runtime/hooks/meta/on-edit-enforce.py (PreToolUse) and
runtime/hooks/meta/on-stop-enforce.py (Stop). Enforces two rules:

1. Authority — edits to product source inside a registered project require an
   in_progress work order in ~/.dream-studio/state/studio.db, and a session
   that edited product source must record at least one authority write
   (task.completed / work_order.closed event, or a fresh row update) before
   it may end.
2. Docstore — persistent documentation artifacts (docs/**) written during a
   session must have a matching ds_files record in ~/.dream-studio/state/files.db.
3. Zero-disk .planning — .planning/** (incl. personal) is docstore-only: authored
   in files.db via `ds files write`, never on disk. Disk writes are denied at edit
   time (WO-FILESDB-P3).

Every public function fails open: any exception yields the permissive result.
Enforcement must never brick an adapter — a broken authority DB means no
enforcement, not no editing. DS_ENFORCE=0 disables everything.

Authority-write detection intentionally accepts EITHER signal direction:
`ds work-order start` updates the business_work_orders row immediately while
its canonical event lands later via spool ingest; `task-done` emits the event
immediately while the business_tasks row lags until sync_tick. Checking both
sides makes same-session detection robust to both lag directions.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

STATE_DIR = Path.home() / ".dream-studio" / "state"
AUTHORITY_DB = STATE_DIR / "studio.db"
FILES_DB = STATE_DIR / "files.db"
SESSION_DIR = STATE_DIR / "enforce"

# Paths never subject to enforcement (module constants so tests can patch them).
DS_HOME = Path.home() / ".dream-studio"
TEMP_ROOT = Path(tempfile.gettempdir())

# Repo-internal directories whose files are never product source.
_EXEMPT_SEGMENTS = frozenset(
    {".git", ".claude", ".venv", "__pycache__", "node_modules", "graphify-out"}
)

_SESSION_FILE_MAX_AGE_SECS = 7 * 24 * 3600


_TIER_ENV = "DS_ENFORCE_TIER"
VALID_TIERS = ("off", "observe", "warn", "enforce")


def resolve_tier() -> str:
    """Resolve the graduated enforcement tier (WO-ENFORCE-TIERS).

    Ladder (least → most intrusive):
      off      — enforcement and its telemetry are entirely disabled.
      observe  — record what WOULD have been denied, then allow the action.
      warn     — observe, and additionally surface the message, then allow.
      enforce  — block the action (the historical behavior).

    Resolution: the legacy total-off switch ``DS_ENFORCE=0`` wins and maps to ``off``
    (so ``off`` and ``DS_ENFORCE=0`` are equivalent). Otherwise ``DS_ENFORCE_TIER`` in
    ``VALID_TIERS``; an unset/invalid value defaults to ``enforce`` — enforcement stays on
    by default, and only an explicit, recognized tier lowers it.
    """
    if os.environ.get("DS_ENFORCE", "").strip() == "0":
        return "off"
    tier = os.environ.get(_TIER_ENV, "").strip().lower()
    return tier if tier in VALID_TIERS else "enforce"


def enforcement_disabled() -> bool:
    """True when enforcement is entirely off. ``DS_ENFORCE=0`` and ``DS_ENFORCE_TIER=off``
    are equivalent (both resolve to the ``off`` tier)."""
    return resolve_tier() == "off"


def record_observation(
    *,
    hook_name: str,
    hook_type: str,
    rule: str,
    reason: str,
    tier: str = "observe",
    session_id: str | None = None,
    started_at: str | None = None,
    duration_ms: int = 0,
    db_path: Path | None = None,
) -> None:
    """Record a would-have-denied action at the observe/warn tier.

    Carries the SAME reason string (including the remediation command) the ``enforce`` tier
    would have emitted, so the observe-mode record is directly comparable to an enforce-mode
    deny. Best-effort, like ``log_hook_execution`` — a broken emit path never affects the
    allow decision. The record rides the existing HOOK_EXECUTION_LOGGED canonical event via
    ``trigger_context`` (no new table)."""
    try:
        from core.event_store.event_writer import insert_hook_execution

        insert_hook_execution(
            hook_name=hook_name,
            hook_type=hook_type,
            trigger_context={
                "decision": "observe",
                "tier": tier,
                "rule": rule,
                "would_deny_reason": reason,
            },
            started_at=started_at or now_iso(),
            completed_at=now_iso(),
            duration_ms=duration_ms,
            exit_code=0,
            status="success",
            session_id=session_id,
            db_path=db_path,
        )
    except Exception:
        pass  # telemetry is best-effort; never let a broken emit affect enforcement


def observations_report(*, since_iso: str | None = None, db_path: Path | None = None) -> dict:
    """Answer 'what would have been blocked, and by which rule' from the observe-mode records.

    Reads the HOOK_EXECUTION_LOGGED observations (decision == observe) from the authority and
    groups them by rule. This is the artifact that earns a team's consent to escalate from
    observe → warn → enforce. Returns
    ``{"since": iso|None, "total": int, "by_rule": {rule: {"count": n, "samples": [...]}}}``.
    """
    target = db_path or AUTHORITY_DB
    conn = _connect_ro(target)
    if conn is None:
        return {"since": since_iso, "total": 0, "by_rule": {}, "note": "authority DB unavailable"}
    try:
        params: list[str] = []
        where = (
            "event_type = 'system.hook.execution.logged'"
            " AND json_extract(payload, '$.trigger_context.decision') = 'observe'"
        )
        if since_iso:
            where += " AND event_timestamp >= ?"
            params.append(since_iso)
        rows = conn.execute(
            "SELECT event_timestamp,"
            " json_extract(payload, '$.trigger_context.rule') AS rule,"
            " json_extract(payload, '$.trigger_context.would_deny_reason') AS reason,"
            " json_extract(payload, '$.hook_name') AS hook_name"
            f" FROM ai_canonical_events WHERE {where} ORDER BY event_timestamp DESC",
            params,
        ).fetchall()
    except sqlite3.Error:
        return {"since": since_iso, "total": 0, "by_rule": {}, "note": "query failed"}
    finally:
        conn.close()

    by_rule: dict[str, dict] = {}
    for row in rows:
        rule = row["rule"] or "unknown"
        bucket = by_rule.setdefault(rule, {"count": 0, "samples": []})
        bucket["count"] += 1
        if len(bucket["samples"]) < 5:
            bucket["samples"].append(
                {"when": row["event_timestamp"], "hook": row["hook_name"], "reason": row["reason"]}
            )
    return {"since": since_iso, "total": len(rows), "by_rule": by_rule}


def record_bypass(
    *,
    hook_name: str,
    hook_type: str,
    rule: str,
    detail: str,
    session_id: str | None = None,
    db_path: Path | None = None,
) -> None:
    """Record an enforcement bypass or fail-open (WO-BYPASS-TELEMETRY).

    Every escape hatch leaves a mark: the DS_ENFORCE=0 / tier=off short-circuit
    and the fail-open allow paths (broken DB, lib import failure) are recorded
    with ``decision == "bypass"`` on the same HOOK_EXECUTION_LOGGED canonical
    event ``record_observation`` uses — no new table, and the writer falls back
    to a text file on DB lock, so a broken authority DB does not also kill the
    signal. Best-effort: a broken emit path never affects the allow decision.
    """
    try:
        from core.event_store.event_writer import insert_hook_execution

        insert_hook_execution(
            hook_name=hook_name,
            hook_type=hook_type,
            trigger_context={
                "decision": "bypass",
                "rule": rule,
                "detail": detail,
            },
            started_at=now_iso(),
            completed_at=now_iso(),
            duration_ms=0,
            exit_code=0,
            status="success",
            session_id=session_id,
            db_path=db_path,
        )
    except Exception:
        pass  # telemetry is best-effort; never let a broken emit affect enforcement


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def log_hook_execution(
    *,
    hook_name: str,
    hook_type: str,
    started_at: str,
    duration_ms: int,
    decision: str,
    status: str = "success",
    error_message: str | None = None,
    session_id: str | None = None,
) -> None:
    """Best-effort emit of HOOK_EXECUTION_LOGGED for a directly-wired enforce hook.

    on-edit-enforce (PreToolUse) and on-stop-enforce (Stop) are wired straight into
    hooks.json rather than through the dispatcher, so — unlike the dispatched hooks,
    which control.execution.dispatch_tracking logs uniformly — their execution was
    never recorded and the DuckDB hook_executions view under-counted the two
    safety-critical hooks (WO-HOOK-ENFORCE-EXEC-STATS).

    Mirrors on-pulse / dispatch_tracking: fire-and-forget to the spool. Never raises
    and never writes stdout — a blocking hook owns its stdout for the deny/allow
    decision, so telemetry must stay silent (lesson edb8525f). The decision is
    carried in trigger_context so the stats surface can distinguish allow/deny.
    """
    try:
        from core.event_store.event_writer import insert_hook_execution

        insert_hook_execution(
            hook_name=hook_name,
            hook_type=hook_type,
            trigger_context={"decision": decision},
            started_at=started_at,
            completed_at=now_iso(),
            duration_ms=duration_ms,
            exit_code=0,
            status=status,
            error_message=error_message,
            session_id=session_id,
        )
    except Exception:
        # Telemetry is best-effort: never let a broken emit path affect enforcement.
        # Narrow to Exception so KeyboardInterrupt/SystemExit still propagate.
        pass


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts


def _connect_ro(db_path: Path) -> sqlite3.Connection | None:
    if not db_path.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=2.0)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error:
        return None


# ---------------------------------------------------------------------------
# Path classification
# ---------------------------------------------------------------------------


def _resolve(path_str: str) -> Path | None:
    try:
        return Path(path_str).expanduser().resolve()
    except (OSError, ValueError):
        return None


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        # Windows paths compare case-insensitively.
        try:
            Path(str(path).lower()).relative_to(Path(str(root).lower()))
            return True
        except ValueError:
            return False


def match_registered_project(file_path: str) -> dict | None:
    """Return {project_id, name, project_path} for the registered project
    containing file_path, or None. Prefers active over paused projects and
    the longest matching project_path."""
    resolved = _resolve(file_path)
    if resolved is None:
        return None
    if _is_under(resolved, DS_HOME) or _is_under(resolved, TEMP_ROOT):
        return None

    conn = _connect_ro(AUTHORITY_DB)
    if conn is None:
        # WO-BYPASS-TELEMETRY: the authority DB is missing/unreadable, so path
        # enforcement silently fails open for EVERY edit. Record the fail-open —
        # the spool write lands on disk first, so a broken DB does not also kill
        # the signal.
        record_bypass(
            hook_name="enforcement_lib",
            hook_type="PreToolUse",
            rule="fail_open_authority_db",
            detail=f"authority DB unavailable at {AUTHORITY_DB} — enforcement fails open",
        )
        return None
    try:
        rows = conn.execute(
            "SELECT project_id, name, status, project_path FROM business_projects"
            " WHERE status IN ('active', 'paused') AND project_path IS NOT NULL"
        ).fetchall()
    except sqlite3.Error:
        record_bypass(
            hook_name="enforcement_lib",
            hook_type="PreToolUse",
            rule="fail_open_authority_query",
            detail="business_projects query failed (locked/corrupt schema) — enforcement fails open",
        )
        return None
    finally:
        conn.close()

    candidates = []
    for row in rows:
        root = _resolve(row["project_path"])
        if root is not None and _is_under(resolved, root):
            candidates.append((row["status"] != "active", -len(str(root)), row))
    if not candidates:
        return None
    best = min(candidates)[2]
    return {
        "project_id": best["project_id"],
        "name": best["name"],
        "project_path": best["project_path"],
    }


def classify_path(file_path: str, project_path: str) -> str:
    """Classify a file inside a project as 'source', 'doc', 'docstore_only', or 'exempt'.

    doc           — persistent documentation artifact: docs/**; must be registered in
                    files.db.
    docstore_only — .planning/** working state (notes, specs, plans, reports, incl.
                    personal): authored in the files.db docstore, NEVER on disk
                    (WO-FILESDB-P3 zero-disk). Disk writes are denied at edit time.
    exempt        — repo-internal noise (.git, .claude, caches); never denied, tracked.
    source        — everything else; requires an in_progress work order.
    """
    resolved = _resolve(file_path)
    root = _resolve(project_path)
    if resolved is None or root is None:
        return "exempt"
    try:
        rel_parts = resolved.relative_to(root).parts
    except ValueError:
        try:
            rel_parts = Path(str(resolved).lower()).relative_to(Path(str(root).lower())).parts
        except ValueError:
            return "exempt"
    if not rel_parts:
        return "exempt"
    if any(part in _EXEMPT_SEGMENTS for part in rel_parts):
        return "exempt"
    if rel_parts[0] == ".planning":
        return "docstore_only"
    if rel_parts[0] == "docs":
        return "doc"
    return "source"


# ---------------------------------------------------------------------------
# Authority queries
# ---------------------------------------------------------------------------


def in_progress_work_order(
    project_id: str,
    *,
    file_path: str | None = None,
    project_path: str | None = None,
) -> dict | None:
    """The in-progress work order an edit belongs to.

    WO-WO-LIFECYCLE-SURFACE: ATTRIBUTE BY BOUNDARY, NOT BY RECENCY. This took the newest
    ``started_at`` and stopped there. With several work orders in progress at once -- which
    the fan-out change made normal, and 3 were in progress on the live authority when this
    was written -- every edit in the session was credited to whichever one happened to be
    started last, regardless of which one's files were being touched.

    That is not a cosmetic mislabel. The stop hook then demands an authority write against
    a work order the session never touched, and the honest responses are both bad: mark a
    task done that is not done, or bypass the hook. It happened while this very function
    was being fixed -- edits to the lifecycle surface were attributed to the workflow-runner
    work order started an hour earlier.

    So when the edited path is known, prefer the in-progress work order whose declared
    ``Module boundary:`` contains it. Recency remains the fallback, because a work order
    with no declared boundary is the common case and refusing to attribute at all would
    turn a mislabel into a block -- but the result SAYS WHICH, so a caller can tell a match
    from a guess rather than reading both as the same claim.
    """
    conn = _connect_ro(AUTHORITY_DB)
    if conn is None:
        return None
    try:
        rows = conn.execute(
            "SELECT work_order_id, title, description FROM business_work_orders"
            " WHERE project_id = ? AND status = 'in_progress'"
            " ORDER BY started_at DESC",
            (project_id,),
        ).fetchall()
    except sqlite3.Error:
        return None
    finally:
        conn.close()

    if not rows:
        return None

    def _as_dict(row: tuple, attribution: str) -> dict:
        return {
            "work_order_id": row[0],
            "title": row[1],
            "description": row[2] or "",
            "attribution": attribution,
        }

    if file_path and project_path:
        matched = [
            row
            for row in rows
            # An empty boundary makes path_in_boundary vacuously true, which would let the
            # first boundaryless work order claim every edit -- exactly the recency bug in
            # a new costume. Only a DECLARED boundary can win a match.
            if boundary_globs(row[2] or "")
            and path_in_boundary(file_path, project_path, boundary_globs(row[2] or ""))
        ]
        if matched:
            chosen = _as_dict(matched[0], "module_boundary")
            # AMBIGUITY IS NOT RESOLVED BY GUESSING. When two in-progress work orders both
            # declare a boundary over this path, both are legitimately doing this work.
            # Every claimant is carried forward so a later check can accept a write to
            # ANY of them; picking a winner would manufacture a false violation against
            # whichever one lost, and a gate that is wrong is a gate that gets disabled.
            chosen["claimants"] = [row[0] for row in matched]
            return chosen

    return _as_dict(rows[0], "most_recently_started")


# ---------------------------------------------------------------------------
# Bash/PowerShell write-target extraction + module-boundary advisory
# (WO-HOOK-COVERAGE — the PreToolUse matcher covered only Edit/Write/MultiEdit/
# NotebookEdit, so any write via Bash, PowerShell, or an MCP write tool bypassed
# enforcement entirely, and module_boundary was never checked anywhere in code.)
# ---------------------------------------------------------------------------

_WRITE_INDICATORS = re.compile(
    r"(?:^|[\s;|&(])("
    r">>?|\btee\b|\bSet-Content\b|\bAdd-Content\b|\bOut-File\b"
    r"|\bgit\s+apply\b|\bcp\b|\bmv\b|\bcopy\b|\bmove\b"
    r")"
    r"|open\([^)]*['\"][wax]",
    re.IGNORECASE,
)

_QUOTED_OR_BARE = r"(?:\"([^\"]+)\"|'([^']+)'|([^\s;|&<>\"']+))"
_REDIRECT_TARGET = re.compile(r"(?<![<>0-9])>{1,2}\s*" + _QUOTED_OR_BARE)
_TEE_TARGET = re.compile(r"\btee\s+(?:-a\s+)?" + _QUOTED_OR_BARE, re.IGNORECASE)
_PS_TARGET = re.compile(
    r"\b(?:Set-Content|Add-Content|Out-File)\s+(?:-Path\s+)?" + _QUOTED_OR_BARE,
    re.IGNORECASE,
)


def extract_write_targets(command: str) -> tuple[list[str], bool]:
    """Best-effort write-target extraction from a shell command.

    Returns ``(targets, has_write_indicators)``. Quoted targets (paths with
    spaces) are captured; targets containing shell variables or substitutions
    are unresolvable and dropped — when indicators exist but no target
    resolved, the caller records an ``unparsed_write`` visibility event and
    allows (fail-open stays; invisibility does not).
    """
    if not command:
        return [], False
    has_indicators = bool(_WRITE_INDICATORS.search(command))
    targets: list[str] = []
    for pattern in (_REDIRECT_TARGET, _TEE_TARGET, _PS_TARGET):
        for match in pattern.finditer(command):
            raw = (match.group(1) or match.group(2) or match.group(3) or "").strip()
            if not raw or raw in ("/dev/null", "NUL", "nul", "&1", "&2"):
                continue
            if any(ch in raw for ch in ("$", "%", "`", "*")):
                continue  # unresolvable at parse time — covered by the indicator flag
            targets.append(raw)
    return list(dict.fromkeys(targets)), has_indicators


def boundary_globs(description: str) -> list[str]:
    """Parse a WO description's ``Module boundary: a, b, c.`` clause into path
    prefixes. Returns [] when no boundary is declared (advisory check skips)."""
    match = re.search(r"Module boundary:\s*([^.]+(?:\.[a-z]+[^.]*)*)", description or "")
    if not match:
        return []
    clause = match.group(1)
    parts = [p.strip().rstrip(".").strip() for p in clause.split(",")]
    return [p for p in parts if p and ("/" in p or "." in p)]


def path_in_boundary(file_path: str, project_path: str, globs: list[str]) -> bool:
    """True when file_path falls under any declared boundary prefix (or no
    boundary is declared). Prefix semantics: 'core/x.py' matches exactly,
    'docs' matches the subtree."""
    if not globs:
        return True
    resolved = _resolve(file_path)
    root = _resolve(project_path)
    if resolved is None or root is None:
        return True
    try:
        rel = resolved.relative_to(root).as_posix()
    except ValueError:
        try:
            rel = Path(str(resolved).lower()).relative_to(Path(str(root).lower())).as_posix()
        except ValueError:
            return True
    rel_lower = rel.lower()
    for g in globs:
        g_norm = g.replace("\\", "/").strip("/").lower()
        if rel_lower == g_norm or rel_lower.startswith(g_norm.rstrip("/") + "/"):
            return True
        # 'tests/unit/test_x.py'-style file prefixes: also accept dirname match.
        if "/" in g_norm and rel_lower.startswith(g_norm.rsplit("/", 1)[0] + "/"):
            return True
    return False


def next_created_work_order(project_id: str) -> dict | None:
    conn = _connect_ro(AUTHORITY_DB)
    if conn is None:
        return None
    try:
        # EXCLUDE CANDIDATES `work-order start` WOULD REFUSE. This selected on
        # status='created' alone, so the DENY it feeds could name a work order blocked
        # behind an unclosed dependency -- start_main.py returns
        # "Cannot start this work order -- N declared dependenc(y/ies) are not closed
        # yet" for exactly that. The operator was denied an edit and handed a command
        # that would also refuse, leaving no forward path. Dependency edges are an
        # ordinary feature (ds work-order add-dep), not a corner case.
        #
        # The design-brief refusal is deliberately NOT modelled here: it is a
        # confirmable prompt (accept_no_brief) rather than a hard stop, so naming such a
        # work order still gives the operator somewhere to go. Excluding only what
        # cannot proceed keeps this from silently hiding startable work.
        row = conn.execute(
            "SELECT wo.work_order_id, wo.title FROM business_work_orders wo"
            " LEFT JOIN business_milestones m ON m.milestone_id = wo.milestone_id"
            " WHERE wo.project_id = ? AND wo.status = 'created'"
            " AND NOT EXISTS ("
            "   SELECT 1 FROM work_order_dependencies d"
            "   JOIN business_work_orders dep ON dep.work_order_id = d.depends_on_id"
            "   WHERE d.work_order_id = wo.work_order_id"
            "   AND dep.status NOT IN ('closed', 'cancelled')"
            " )"
            " ORDER BY m.order_index ASC, wo.sequence_order ASC NULLS LAST,"
            " wo.created_at ASC LIMIT 1",
            (project_id,),
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    return {"work_order_id": row[0], "title": row[1]} if row else None


# WO-HOOK-WRITE-ACCOUNTING. The statuses a completed task actually carries.
#
# The reader asked for status = 'done' while `ds work-order task-done` writes
# 'complete' (core/projections/task_projection.py). In the live authority that is
# 2,058 'complete' rows against 27 'done' — all legacy, last written 2026-06-29 — so
# the row fallback had matched nothing for months. Four consecutive successful
# task-done calls on befde290 were then reported as "no authority write was recorded
# this session": the writes landed and the reader could not see them.
#
# BOTH are accepted, not one literal swapped for another: 'complete' for current
# writes, 'done' so the historical rows keep counting. This is not imported from
# core because this module is copied verbatim into the installed hook trees and may
# only use the stdlib — so drift is prevented by a test that drives the REAL
# mark_task_done and asserts the status it produces is in this set, rather than by an
# import that cannot exist here.
TASK_DONE_STATUSES = ("complete", "done")

# Artifact kinds that ARE an authority write. `ds work-order affirm-impact` stores an
# impact_affirmation and satisfies the change_impact_affirmed close gate, so it is
# unambiguously recorded work — but the reader did not count it, and a session whose
# only honest remaining write is an affirmation then had NO truthful way to satisfy
# the hook: every task already complete, and close blocked on a gate. Hit three times
# on 2026-08-19/20 (758fbedd, c14c2eea, 66e7ebc8). Deliberately narrow — a verdict or
# a report is evidence ABOUT work, not a record that work was completed.
AUTHORITY_ARTIFACT_KINDS = ("impact_affirmation",)


def incomplete_task_count(work_order_id: str) -> int | None:
    """How many tasks remain markable, or None when the authority cannot be read.

    Exists so the stop hook never prescribes a command the operator cannot run. Its
    message offered exactly two remedies -- ``task-done <task_id>`` and ``close`` -- and
    on the session that produced this function BOTH were impossible: ten tasks, all
    complete, and close refused by its gates. The only ways left to stop were to invent
    a task and mark it done, which is the false-done this module exists to prevent, or
    to disable enforcement. A gate whose remedy cannot be performed drives the operator
    to exactly the two outcomes it was built to stop.

    None (unreadable) is distinct from 0 (readable, nothing left) because the caller
    must not claim "no tasks remain" on the strength of a failed query -- that would be
    the compared-nothing-reported-clean shape this codebase keeps finding.
    """
    conn = _connect_ro(AUTHORITY_DB)
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT COUNT(*),"
            " SUM(CASE WHEN status NOT IN ('complete', 'done', 'cancelled') THEN 1 ELSE 0 END)"
            " FROM business_tasks WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    if row is None or not row[0]:
        # No tasks at all -- including an unknown work order id, which the count query
        # answers 0 for just as readily as a real one. Reporting 0 here would let the
        # caller announce "every task is already complete" about a work order that has
        # none, so this stays None: not knowing is not the same as nothing remaining.
        return None
    return int(row[1] or 0)


def authority_write_since(work_order_id: str, since_iso: str) -> bool:
    """True if any authority write for the WO landed at/after since_iso.

    DURABLE ROW STATE IS THE PRIMARY SIGNAL, canonical events are reinforcement.
    The original order asked the event stream first, and events arrive only once
    spool ingestion has run — so the check partly measured "did ingestion keep up"
    rather than "did the operator record work", and a compliant session was blocked
    whenever ingestion lagged. The rows are written by the mutation itself and cannot
    lag it. Same demotion the verify locator got: read the state, treat the stream as
    corroboration.
    """
    since = parse_ts(since_iso)
    if since is None:
        return True  # unusable window — fail open
    conn = _connect_ro(AUTHORITY_DB)
    if conn is None:
        return True
    try:
        # 1. A completed task — the most common authority write by far.
        placeholders = ",".join("?" for _ in TASK_DONE_STATUSES)
        rows = conn.execute(
            "SELECT updated_at FROM business_tasks"
            f" WHERE work_order_id = ? AND status IN ({placeholders})",
            (work_order_id, *TASK_DONE_STATUSES),
        ).fetchall()
        for row in rows:
            ts = parse_ts(row[0])
            if ts is not None and ts >= since:
                return True

        # 1b. A task CREATED in the window. Registering newly discovered work is as much
        # an authority write as completing it, and the no-deferred-findings rule REQUIRES
        # registering a defect the moment it is found. Without this, a session whose
        # honest output is "I found and registered three defects" reads as having
        # recorded nothing -- measured on the session that produced this fix, which
        # registered six work orders and eight tasks and still tripped the hook.
        rows = conn.execute(
            "SELECT created_at FROM business_tasks WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchall()
        for row in rows:
            ts = parse_ts(row[0])
            if ts is not None and ts >= since:
                return True

        # 2. An artifact whose existence records completed work (impact affirmation).
        placeholders = ",".join("?" for _ in AUTHORITY_ARTIFACT_KINDS)
        try:
            rows = conn.execute(
                "SELECT updated_at, created_at FROM business_work_order_artifacts"
                f" WHERE work_order_id = ? AND kind IN ({placeholders})",
                (work_order_id, *AUTHORITY_ARTIFACT_KINDS),
            ).fetchall()
        except sqlite3.Error:
            rows = []  # table absent on an old authority — not a reason to block
        for row in rows:
            ts = parse_ts(row[0]) or parse_ts(row[1])
            if ts is not None and ts >= since:
                return True

        # 3. The work order itself reached a terminal state.
        row = conn.execute(
            "SELECT status, closed_at FROM business_work_orders WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if row is not None and row[0] in ("closed", "cancelled"):
            return True

        # 4. Reinforcement: the canonical event stream, which lags behind the rows
        # above by however long spool ingestion takes. Last because a write that has
        # not been ingested yet is still a write.
        rows = conn.execute(
            "SELECT event_timestamp, received_at FROM business_canonical_events"
            " WHERE work_order_id = ?"
            " AND event_type IN ('task.completed', 'work_order.closed')",
            (work_order_id,),
        ).fetchall()
        for row in rows:
            ts = parse_ts(row[0]) or parse_ts(row[1])
            if ts is not None and ts >= since:
                return True
    except sqlite3.Error:
        return True
    finally:
        conn.close()
    return False


def docstore_record_since(name_hint: str, since_iso: str) -> bool:
    """True if a ds_files record whose name contains name_hint landed at/after since_iso."""
    since = parse_ts(since_iso)
    if since is None:
        return True
    conn = _connect_ro(FILES_DB)
    if conn is None:
        return False  # no docstore at all — the artifact cannot be registered
    try:
        rows = conn.execute(
            "SELECT created_at FROM ds_files WHERE name LIKE ?",
            (f"%{name_hint}%",),
        ).fetchall()
    except sqlite3.Error:
        return True
    finally:
        conn.close()
    for row in rows:
        ts = parse_ts(row[0])
        if ts is not None and ts >= since:
            return True
    return False


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------


def _session_file(session_id: str) -> Path:
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_")[:80]
    return SESSION_DIR / f"{safe}.json"


def load_session(session_id: str) -> dict | None:
    path = _session_file(session_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_session(session_id: str, data: dict) -> None:
    try:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        _session_file(session_id).write_text(json.dumps(data, indent=1), encoding="utf-8")
    except OSError:
        pass


def delete_session(session_id: str) -> None:
    try:
        _session_file(session_id).unlink(missing_ok=True)
    except OSError:
        pass


def gc_session_files() -> None:
    """Best-effort cleanup of stale session files from sessions that never stopped."""
    try:
        cutoff = time.time() - _SESSION_FILE_MAX_AGE_SECS
        for path in list(SESSION_DIR.glob("*.json"))[:200]:
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
    except OSError:
        pass


def record_edit(
    session_id: str,
    *,
    file_path: str,
    kind: str,
    project_id: str,
    work_order_id: str | None,
    claimants: list[str] | None = None,
) -> None:
    """Record an allowed edit so on-stop-enforce can check the session's writes.

    ``claimants`` is every in-progress work order whose declared module boundary contains
    this path. The stop check is satisfied by an authority write to any of them: where two
    work orders both legitimately claim a file, demanding a write to the one this hook
    happened to name would be a false violation, and false violations are what push an
    operator to DS_ENFORCE=0.
    """
    data = load_session(session_id) or {
        "session_id": session_id,
        "started_at": now_iso(),
        "source_edits": [],
        "doc_edits": [],
        "stop_blocked_at": None,
    }
    bucket = data.setdefault("source_edits" if kind == "source" else "doc_edits", [])
    normalized = str(_resolve(file_path) or file_path)
    for entry in bucket:
        if entry.get("path") == normalized:
            entry["work_order_id"] = work_order_id
            entry["claimants"] = list(claimants or ([work_order_id] if work_order_id else []))
            entry["ts"] = now_iso()
            break
    else:
        if len(bucket) < 500:
            bucket.append(
                {
                    "path": normalized,
                    "project_id": project_id,
                    "work_order_id": work_order_id,
                    "claimants": list(claimants or ([work_order_id] if work_order_id else [])),
                    "ts": now_iso(),
                }
            )
    save_session(session_id, data)
