"""Work-order independent verification via parallel fresh-context graders.

Entry point: ``verify_work_order(work_order_id=, source_root=, dream_studio_home=)``.

Architecture (T4c/T4d/T4e):
Four independent graders run in parallel via subprocess.Popen. Each grader is
blind to the other graders' domain — no shared context between prompts:

  Grader 1 — Completion: task list + git diff.
    Returns: {passed, tasks_verified, summary, gaps, completion_score}

  Grader 2 — Correctness: architectural rules + git diff only (NO task list).
    Returns: {correctness_passed, correctness_score, violations, coverage_gaps,
              migration_gaps}

  Grader 3 — Quality: quality best-practice rules + git diff only (NO task list).
    Returns: {quality_passed, quality_score, issues}

  Grader 4 — Migration (only when diff contains migration files): migration SQL
    file contents only (NO task list, NO other diff).
    Returns: {migration_safe, migration_score, risks}

Overall pass = completion_passed AND correctness_passed AND composite >= 0.70
  AND migration_safe (when applicable).

Composite score = (completion * 0.5) + (correctness * 0.3) + (quality * 0.2).

Thresholds:
  >= 0.85: auto-continue to next WO
  0.70-0.84: auto-continue with logged warning
  < 0.70: register remediation WO, do NOT auto-continue

Set DREAM_STUDIO_VERIFY_MOCK=1 to substitute deterministic fixtures for CI.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect

_MOCK_ENV = "DREAM_STUDIO_VERIFY_MOCK"

# ── Mock fixtures (one per grader) ─────────────────────────────────────────────

_MOCK_COMPLETION: dict[str, Any] = {
    "passed": True,
    "tasks_verified": [],
    "summary": "[mock] completion grader — DREAM_STUDIO_VERIFY_MOCK=1",
    "gaps": [],
    "completion_score": 1.0,
}

_MOCK_CORRECTNESS: dict[str, Any] = {
    "correctness_passed": True,
    "correctness_score": 1.0,
    "violations": [],
    "coverage_gaps": [],
    "migration_gaps": [],
}

_MOCK_QUALITY: dict[str, Any] = {
    "quality_passed": True,
    "quality_score": 1.0,
    "issues": [],
}

_MOCK_MIGRATION: dict[str, Any] = {
    "migration_safe": True,
    "migration_score": 1.0,
    "risks": [],
}

# Backward-compat alias used by callers that imported _MOCK_FIXTURE directly.
_MOCK_FIXTURE: dict[str, Any] = {
    "passed": True,
    "tasks_verified": [],
    "summary": "[mock] verification fixture — DREAM_STUDIO_VERIFY_MOCK=1",
    "gaps": [],
    "correctness_signals": {
        "architecture_violations": [],
        "coverage_gaps": [],
        "migration_gaps": [],
        "correctness_passed": True,
    },
}

# ── Grader 1 — Completion prompt ───────────────────────────────────────────────

_COMPLETION_PROMPT_TEMPLATE = """You are an independent code reviewer with no prior context about this work order.

Work order: {title}
Work order ID: {work_order_id}
Work order type: {work_order_type}

Tasks that were supposed to be completed:
{task_list}

IMPORTANT — SQL-CHECK RESULTS: Any task line annotated with "SQL-CHECK RESULT: PASS" or
"SQL-CHECK RESULT: FAIL" was verified by executing a SQL query directly against the authority
database. These results are ground truth — they take precedence over diff inference.
A task with SQL-CHECK RESULT: FAIL MUST receive verdict "missing" regardless of what the diff shows.
A task with SQL-CHECK RESULT: PASS may still receive "partial" if the diff evidence is otherwise
incomplete, but the SQL check passing is strong evidence of completion.

Git commits and diffs for this work order:
{git_diff}

Review each task against the commits and diffs above.
Return ONLY valid JSON with this exact schema (no prose, no markdown fences):
{{
  "passed": <bool: true if ALL tasks have verdict "pass">,
  "completion_score": <float 0.0-1.0: tasks_with_verdict_pass / total_tasks>,
  "tasks_verified": [
    {{
      "task_title": "<task title>",
      "evidence": "<one sentence describing what in the diff addresses this task, or why it is missing>",
      "verdict": "pass" | "partial" | "missing"
    }}
  ],
  "summary": "<2-3 sentence overall assessment>",
  "gaps": [
    {{
      "title": "<imperative title for the gap work order>",
      "category": "<short stable slug naming the underlying gap, e.g. 'missing-tests' or 'task-3-incomplete'; keep it identical across re-reviews of the same gap so it dedups even if the title is reworded>",
      "description": "<what needs to be done and why, including what was missed>",
      "work_order_type": "cleanup" | "infrastructure" | "documentation",
      "tasks": [
        {{
          "title": "<imperative task title>",
          "description": "<specific acceptance criteria>"
        }}
      ]
    }}
  ]
}}

A gap entry is required for every task with verdict "partial" or "missing".
If all tasks pass, return gaps as an empty array.

GROUNDING RULE — NO INVENTED THRESHOLDS: Only flag a gap against the EXPLICIT
acceptance-criteria text shown for each task above. Do NOT fabricate numeric
thresholds (line counts, coverage percentages, file-size limits, etc.) that do
not literally appear in a task's acceptance criteria. If the AC does not state a
number, you may not invent one as the basis for a gap.

BEHAVIORAL AC CHECK (warning only, never causes passed=false):
If the work_order_type is "feature" or "infrastructure" AND none of the task descriptions
contain observable end-to-end behavioral acceptance criteria (what the operator sees or
experiences — e.g., a phrase like "Acceptance:", "operator can", "user can", "returns X
when", "emits Y spool event", "CLI outputs") — add one warning-severity gap:
{{
  "title": "Add observable behavioral acceptance criteria to task descriptions",
  "description": "No task in this work order describes end-to-end observable behavior from the operator's perspective. Tasks should include at least one AC statement like 'Acceptance: <what the operator experiences>'. This is a documentation gap; it does not affect code correctness.",
  "work_order_type": "documentation",
  "tasks": [{{ "title": "Add behavioral AC to task descriptions", "description": "Rewrite each task description to include an Acceptance: clause stating what the operator observes when the task is done correctly." }}]
}}
Do NOT emit this gap if: (a) behavioral AC is already present, (b) work_order_type is not
feature/infrastructure, or (c) the gap would duplicate a task-level gap already in the list.
"""

# ── Grader 2 — Correctness prompt (no task list) ───────────────────────────────

_CORRECTNESS_PROMPT_TEMPLATE = """You are an independent architectural reviewer.
You have NO information about what tasks were supposed to be completed.
Grade the diff below ONLY against the architectural rules listed here.

Git diff to review:
{git_diff}

Rules to check (flag violations, not warnings — be precise):
(1) THREE-STORE ARCHITECTURE: SQLite studio.db is for business_* and event-spine tables only. DuckDB is for analytics projections. files.db is for artifact blobs. Flag: analytics code reading from SQLite instead of DuckDB. NOTE: core/projections/ modules are EXPECTED to write to business_* tables — they materialize canonical events into business read models. Do NOT flag projection writes to business_* as violations.
(2) LAYER-MAP Rule 1: runtime/hooks/ must not write to authority tables (business_*, raw_*).
(3) LAYER-MAP Rule 2: projections/ modules must be read-only against CANONICAL EVENT tables (business_canonical_events, ai_canonical_events). Projections may and should write to business_* read-model tables as part of event materialization.
(4) LAYER-MAP Rule 3: business_* writes must come only from interfaces/cli/, core/work_orders/, OR core/projections/ (canonical event handlers only — not ad-hoc writes outside an event handler method).
(5) LAYER-MAP Rule 4: canonical_events must only be written by spool/ingestor.py.
(6) TEST COVERAGE: new public functions or CLI commands added without corresponding tests; existing tests deleted without replacement.
(7) MIGRATION HYGIENE (only if the diff adds a migration file): migration file added? released_version bumped? aspirational-schema-debt.md updated?
(8) DEAD TABLE RESURRECTION: test diffs that add CREATE TABLE (or CREATE TABLE IF NOT EXISTS) for any table explicitly dropped in a numbered migration file are a violation. A dropped table has no production code creating it; the fixture would simulate a DB state that can never exist in reality. The correct fix is to DELETE the test (dead subject) or fix the root cause in the migration — never feed dead-table fixtures to keep the test alive.

Return ONLY valid JSON (no prose, no markdown fences):
{{
  "correctness_passed": <bool: true only if violations, coverage_gaps, and migration_gaps are ALL empty>,
  "correctness_score": <float 0.0-1.0: 1.0 if no violations, else max(0.0, 1.0 - violation_count / 7.0)>,
  "violations": [
    {{
      "rule": "<rule number and name, e.g. 'Rule 3: business_* writes'>",
      "file": "<file path from diff>",
      "line": "<line number or N/A>",
      "detail": "<one sentence explaining the violation>"
    }}
  ],
  "coverage_gaps": [
    {{
      "function": "<function or command name>",
      "file": "<file path>"
    }}
  ],
  "migration_gaps": [
    {{
      "item": "<what is missing, e.g. released_version not bumped>"
    }}
  ]
}}
"""

# ── Grader 3 — Quality prompt (no task list) ───────────────────────────────────

_QUALITY_PROMPT_TEMPLATE = """You are an independent code quality reviewer.
You have NO information about what tasks were supposed to be completed or what architectural rules apply.
Grade the diff below ONLY against quality best practices.

Git diff to review:
{git_diff}

Quality rules:
(1) SECURITY: parameterized queries only — flag f-string or .format() SQL; no secrets or API keys in code; no bare eval(); no subprocess with shell=True on unsanitized input.
(2) ERROR HANDLING: no bare except: clauses; no exceptions swallowed without logging; no silent failure on DB writes.
(3) TYPE SAFETY: new public functions must have type annotations on parameters and return value.
(4) API DESIGN: new routes must return consistent response shapes, correct HTTP status codes, all error paths have responses.
(5) TEST QUALITY: tests must assert behavior not implementation; no tests that only check a function was called without checking its effect on state.
(6) SQL PATTERNS: unbounded SELECT on large tables must have LIMIT; no N+1 query patterns in loops.

Return ONLY valid JSON (no prose, no markdown fences):
{{
  "quality_passed": <bool: true if no error-severity issues>,
  "quality_score": <float 0.0-1.0: 1.0 if no issues, subtract 0.1 per error, 0.03 per warning, floor at 0.0>,
  "issues": [
    {{
      "category": "<rule name: SECURITY | ERROR_HANDLING | TYPE_SAFETY | API_DESIGN | TEST_QUALITY | SQL_PATTERNS>",
      "file": "<file path from diff>",
      "line": "<line number or N/A>",
      "detail": "<one sentence describing the issue>",
      "severity": "warning" | "error"
    }}
  ]
}}
"""

# ── Grader 4 — Migration prompt (migration SQL only) ──────────────────────────

_MIGRATION_PROMPT_TEMPLATE = """You are a database migration safety reviewer.
You receive ONLY a migration SQL file. Grade it for safety and reversibility.
You have no other context about the change.

Migration file: {migration_file}

Migration SQL:
{migration_sql}

Check for:
(1) DATA_LOSS: DROP TABLE or DROP COLUMN without confirming rows=0 or backup; DELETE without WHERE; TRUNCATE.
(2) REVERSIBILITY: irreversible DDL — column type changes; NOT NULL additions without a DEFAULT; DROP COLUMN.
(3) REFERENTIAL_INTEGRITY: dropping a table referenced by FK elsewhere; adding FK to table with potential orphan rows.
(4) MIGRATION_ORDER: dependencies on a prior migration being applied; incorrect sequence.

Return ONLY valid JSON (no prose, no markdown fences):
{{
  "migration_safe": <bool: false if any error-severity risk exists>,
  "migration_score": <float 0.0-1.0: 1.0 if no risks, subtract 0.25 per error, 0.08 per warning, floor at 0.0>,
  "risks": [
    {{
      "category": "DATA_LOSS" | "REVERSIBILITY" | "REFERENTIAL_INTEGRITY" | "MIGRATION_ORDER",
      "detail": "<one sentence describing the risk>",
      "severity": "warning" | "error"
    }}
  ]
}}
"""


# ── DB helpers ─────────────────────────────────────────────────────────────────


def _require_db(source_root: Path, dream_studio_home: Path | None) -> Path:
    from interfaces.cli.ds import resolve_installed_runtime_paths

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing.")
    return paths.sqlite_path


def _read_tasks(conn: Any, work_order_id: str) -> list[dict[str, str]]:
    has_ac = any(
        r[1] == "acceptance_criteria"
        for r in conn.execute("PRAGMA table_info(business_tasks)").fetchall()
    )
    cols = "title, description, status" + (", acceptance_criteria" if has_ac else "")
    rows = conn.execute(
        f"SELECT {cols} FROM business_tasks WHERE work_order_id = ? ORDER BY created_at ASC",
        (work_order_id,),
    ).fetchall()
    return [
        {
            "title": r[0],
            "description": r[1] or "",
            "status": r[2],
            "acceptance_criteria": (r[3] or "") if has_ac else "",
        }
        for r in rows
    ]


def _read_work_order(conn: Any, work_order_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT work_order_id, title, project_id, milestone_id, sequence_order, work_order_type"
        " FROM business_work_orders WHERE work_order_id = ?",
        (work_order_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "work_order_id": row[0],
        "title": row[1],
        "project_id": row[2],
        "milestone_id": row[3],
        "sequence_order": row[4],
        "work_order_type": row[5],
    }


# ── SQL-CHECK executor ─────────────────────────────────────────────────────────


def _run_sql_checks(tasks: list[dict[str, Any]], db_path: Path) -> dict[str, list[dict[str, Any]]]:
    """Execute SQL-CHECK lines from task acceptance_criteria read-only against the authority DB.

    Convention: a line in acceptance_criteria starting with ``SQL-CHECK:`` (case-insensitive)
    followed by a SELECT statement. The check passes if the query returns at least one row
    with a truthy first-column value (e.g. a non-zero COUNT). Fails on zero/null/no rows or
    on any query error.

    Returns a mapping of task_title -> list of {sql, passed, result, error}.
    Only tasks that have at least one SQL-CHECK line produce an entry.
    """
    import sqlite3 as _sqlite3

    results: dict[str, list[dict[str, Any]]] = {}
    try:
        conn = _sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception:
        return {}

    try:
        for task in tasks:
            ac = task.get("acceptance_criteria", "") or ""
            checks: list[dict[str, Any]] = []
            for raw_line in ac.splitlines():
                line = raw_line.strip()
                if not line.upper().startswith("SQL-CHECK:"):
                    continue
                sql = line[len("SQL-CHECK:") :].strip()  # noqa: E203
                check: dict[str, Any] = {
                    "sql": sql,
                    "passed": False,
                    "result": None,
                    "error": None,
                }
                try:
                    row = conn.execute(sql).fetchone()
                    if row is not None:
                        val = row[0]
                        check["result"] = val
                        check["passed"] = bool(val)
                    # else: no rows → passed stays False
                except Exception as exc:
                    check["error"] = str(exc)
                checks.append(check)
            if checks:
                results[task["title"]] = checks
    finally:
        conn.close()

    return results


def _format_sql_checks(checks: list[dict[str, Any]]) -> str:
    """Render SQL-CHECK results as annotated lines for the completion grader prompt."""
    if not checks:
        return ""
    lines: list[str] = []
    for c in checks:
        if c.get("error"):
            lines.append(f"\n   SQL-CHECK RESULT: FAIL (error: {c['error']})")
        elif c["passed"]:
            lines.append(f"\n   SQL-CHECK RESULT: PASS (result={c['result']})")
        else:
            lines.append(f"\n   SQL-CHECK RESULT: FAIL (result={c['result']})")
    return "".join(lines)


# ── Executable check runner (SQL-CHECK / TEST-CHECK / API-CHECK) ───────────────

_CHECK_PREFIXES = ("SQL-CHECK:", "TEST-CHECK:", "API-CHECK:")

# Timeout in seconds for TEST-CHECK subprocess calls.
_TEST_CHECK_TIMEOUT = 300

# ── SQL-CHECK semantics (authoritative — see also docs/authoring/work-orders.md) ──
#
# A SQL-CHECK acceptance criterion MUST be written in the form:
#
#   SQL-CHECK: SELECT 1 WHERE <condition>
#
# so that a FALSE condition yields ZERO rows, which is an explicit HARD FAIL.
#
# HARD FAIL cases:
#   1. Zero rows returned — the WHERE condition evaluated to false (or no table rows
#      matched).  Error message: "SQL-CHECK returned no rows — condition false".
#   2. The first column value is falsy (NULL, 0, empty string).
#   3. The query raises an exception.
#
# PASS: exactly one or more rows are returned AND the first column value is truthy.
#
# Discouraged (but still handled) form:
#   SQL-CHECK: SELECT COUNT(*) FROM t WHERE cond
#
# COUNT(*) always returns one row, so "zero rows = fail" cannot fire.  A COUNT
# of zero (falsy) still fails via case 2, but a COUNT of 1 passes even when only
# a single incidentally-matching row exists — this masks bulk/threshold errors.
# Prefer the SELECT 1 WHERE form so false conditions yield zero rows.


def _run_one_sql_check(expr: str, db_path: Path) -> dict[str, Any]:
    """Execute a single SQL-CHECK expression.  Returns {kind, expr, passed, result, error}.

    Zero rows returned is an explicit HARD FAIL — it means the WHERE condition
    evaluated to false.  Use ``SELECT 1 WHERE <condition>`` so that a false
    condition yields zero rows = fail.  ``COUNT(*)`` forms always return one row
    and cannot trigger the zero-row fail path; they are discouraged.
    """
    import sqlite3 as _sqlite3

    check: dict[str, Any] = {
        "kind": "SQL-CHECK",
        "expr": expr,
        "passed": False,
        "result": None,
        "error": None,
    }
    try:
        conn = _sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = conn.execute(expr).fetchone()
            if row is None:
                # HARD FAIL: zero rows — condition evaluated to false.
                check["error"] = "SQL-CHECK returned no rows — condition false"
            else:
                val = row[0]
                check["result"] = val
                check["passed"] = bool(val)
        finally:
            conn.close()
    except Exception as exc:
        check["error"] = str(exc)
    return check


def _run_one_test_check(expr: str) -> dict[str, Any]:
    """Run a TEST-CHECK by executing the given pytest node-id in a subprocess.

    Uses ``sys.executable`` so it always resolves to the current interpreter — no
    ``shell=True``, Windows-safe.  The node-id may optionally be prefixed with
    ``tests/`` or another path; it is passed verbatim to pytest.

    Returns {kind, expr, passed, result, error}.
    """
    check: dict[str, Any] = {
        "kind": "TEST-CHECK",
        "expr": expr,
        "passed": False,
        "result": None,
        "error": None,
    }
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", expr, "-q", "--tb=short", "--no-header"],
            capture_output=True,
            text=True,
            timeout=_TEST_CHECK_TIMEOUT,
        )
        stdout = (result.stdout or "") + (result.stderr or "")
        check["result"] = stdout[:2000]
        check["passed"] = result.returncode == 0
        if result.returncode != 0:
            check["error"] = f"pytest exited with code {result.returncode}"
    except subprocess.TimeoutExpired:
        check["error"] = f"TEST-CHECK timed out after {_TEST_CHECK_TIMEOUT}s"
    except Exception as exc:
        check["error"] = str(exc)
    return check


def _run_one_api_check(expr: str) -> dict[str, Any]:
    """Run an API-CHECK by booting the FastAPI app via TestClient and issuing the request.

    Syntax: ``METHOD path -> expectation``  (expectation is optional)
    Examples::

        GET /api/health -> 200
        GET /api/health

    The check passes if:
    - The import of ``projections.api.main.app`` succeeds (fail-closed otherwise).
    - The HTTP status is 2xx, OR equals the explicitly stated expected status.
    - The response body is non-empty.

    Returns {kind, expr, passed, result, error}.
    """
    check: dict[str, Any] = {
        "kind": "API-CHECK",
        "expr": expr,
        "passed": False,
        "result": None,
        "error": None,
    }

    # Parse the expression: "METHOD path [-> expected_status]"
    import re as _re

    m = _re.match(r"^(\w+)\s+(\S+)(?:\s*->\s*(\S+))?$", expr.strip())
    if not m:
        check["error"] = f"API-CHECK: unparseable expression: {expr!r}"
        return check

    method = m.group(1).upper()
    path = m.group(2)
    expectation = m.group(3)  # may be None

    # Determine expected status code.
    expected_status: int | None = None
    if expectation is not None:
        try:
            expected_status = int(expectation)
        except ValueError:
            check["error"] = f"API-CHECK: non-integer expectation {expectation!r}"
            return check

    # Import the app — fail-closed if unavailable.
    try:
        from projections.api.main import app as _api_app  # type: ignore[import]
        from fastapi.testclient import TestClient as _TC
    except Exception as exc:
        check["error"] = f"API-CHECK: could not import projections.api.main — {exc}"
        return check

    try:
        client = _TC(_api_app, raise_server_exceptions=False)
        method_fn = getattr(client, method.lower(), None)
        if method_fn is None:
            check["error"] = f"API-CHECK: unsupported HTTP method {method!r}"
            return check
        resp = method_fn(path)
        body = resp.text or ""
        check["result"] = {"status_code": resp.status_code, "body_preview": body[:500]}

        if expected_status is not None:
            status_ok = resp.status_code == expected_status
        else:
            status_ok = 200 <= resp.status_code < 300

        body_ok = bool(body.strip())
        check["passed"] = status_ok and body_ok
        if not status_ok:
            check["error"] = (
                f"API-CHECK: expected status {expected_status or '2xx'}, got {resp.status_code}"
            )
        elif not body_ok:
            check["error"] = "API-CHECK: response body was empty"
    except Exception as exc:
        check["error"] = f"API-CHECK: request failed — {exc}"

    return check


def run_executable_checks(
    tasks: list[dict[str, Any]],
    db_path: Path,
    source_root: Path | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Execute all executable checks (SQL-CHECK / TEST-CHECK / API-CHECK) across tasks.

    Iterates every task's ``acceptance_criteria`` field.  Lines that start with a
    recognised ``*-CHECK:`` prefix are dispatched to the appropriate runner.  Lines
    with an unrecognised ``*-CHECK:`` token (e.g. ``UNKNOWN-CHECK:``) are recorded as
    **failed** (fail-closed).  Lines without any ``*-CHECK:`` token are ignored.

    Returns a mapping of ``task_title -> list[{kind, expr, passed, result, error}]``.
    Only tasks that have at least one executable check line produce an entry.

    :param tasks: list of task dicts with ``title`` and ``acceptance_criteria`` keys.
    :param db_path: path to the authority SQLite DB (used by SQL-CHECK).
    :param source_root: repo root (reserved for future use; currently unused).
    """
    import re as _re

    results: dict[str, list[dict[str, Any]]] = {}

    for task in tasks:
        ac = task.get("acceptance_criteria", "") or ""
        checks: list[dict[str, Any]] = []

        for raw_line in ac.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            # Detect any "*-CHECK:" token in this line.
            token_match = _re.match(r"^([A-Z][A-Z0-9_]*-CHECK):\s*(.*)", line, _re.IGNORECASE)
            if token_match is None:
                continue

            token = token_match.group(1).upper()
            expr = token_match.group(2).strip()

            if token == "SQL-CHECK":
                checks.append(_run_one_sql_check(expr, db_path))
            elif token == "TEST-CHECK":
                checks.append(_run_one_test_check(expr))
            elif token == "API-CHECK":
                checks.append(_run_one_api_check(expr))
            else:
                # Unknown *-CHECK token — fail-closed.
                checks.append(
                    {
                        "kind": token,
                        "expr": expr,
                        "passed": False,
                        "result": None,
                        "error": f"Unknown check kind: {token!r} — fail-closed",
                    }
                )

        if checks:
            results[task["title"]] = checks

    return results


# ── Git diff collection ─────────────────────────────────────────────────────────


def _collect_git_commits(
    source_root: Path, work_order_id: str, title: str | None = None
) -> str | None:
    """Collect commit diffs referencing this work order.

    Searches git history using multiple patterns so squash-merged WOs are still
    found even when the commit subject does not carry the UUID:

    1. Full UUID (``work_order_id``) — exact match.
    2. Short 8-char id (``work_order_id[:8]``) — legacy and short-log references.
    3. ``Work-Order: <uuid>`` trailer in commit body — squash-merge convention.
    4. WO title token (the part before ' - ', e.g. 'WO-DEBT-I') — squash-merge
       subjects carry the WO name.
    5. Branch name containing the short id — commits reachable from a branch whose
       name includes the WO id fragment.

    Returns None when no pattern matches: callers must treat this as "no evidence",
    NOT as a certified pass and NOT as an auto-score-0 verdict.
    """
    full_id = work_order_id
    short_id = work_order_id[:8]
    trailer_pattern = f"Work-Order: {full_id}"

    # Build ordered pattern list (most precise first).
    patterns: list[str] = [full_id, short_id, trailer_pattern]
    if title:
        token = title.split(" - ")[0].strip()
        if token and token not in patterns:
            patterns.append(token)

    try:
        lines: list[str] = []
        for pattern in patterns:
            log_result = subprocess.run(
                ["git", "log", "--all", "--fixed-strings", f"--grep={pattern}", "--format=%H"],
                cwd=str(source_root),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if log_result.stdout.strip():
                lines = log_result.stdout.strip().splitlines()
                break  # Stop at the first pattern that finds commits.

        # Pattern 5: branch-name grep — find branches whose name contains the short id,
        # then collect commits reachable from those branches only (not already found).
        if not lines:
            try:
                branch_result = subprocess.run(
                    ["git", "branch", "--all", "--format=%(refname:short)"],
                    cwd=str(source_root),
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                matching_branches = [
                    b.strip()
                    for b in branch_result.stdout.splitlines()
                    if short_id in b or full_id in b
                ]
                for branch in matching_branches[:3]:
                    log_result = subprocess.run(
                        ["git", "log", branch, "--format=%H", "--max-count=20"],
                        cwd=str(source_root),
                        capture_output=True,
                        text=True,
                        timeout=15,
                    )
                    if log_result.stdout.strip():
                        lines = log_result.stdout.strip().splitlines()
                        break
            except Exception:
                pass  # Branch lookup is best-effort; fall through to None.

        if not lines:
            return None

        diff_parts: list[str] = []
        for commit_hash in lines[:10]:
            commit_hash = commit_hash.strip()
            if not commit_hash:
                continue
            show_result = subprocess.run(
                ["git", "show", "--stat", "--patch", "--no-color", commit_hash],
                cwd=str(source_root),
                capture_output=True,
                text=True,
                timeout=30,
            )
            diff_parts.append(f"=== commit {commit_hash} ===\n{show_result.stdout[:8000]}")
        return "\n\n".join(diff_parts) if diff_parts else None
    except Exception as exc:
        return f"(error collecting git commits: {exc})"


def _find_migration_files(source_root: Path, git_diff: str) -> list[Path]:
    """Return migration SQL files referenced in the git diff.

    The filename portion comes from untrusted git-diff text, so each candidate is
    resolved and confirmed to live inside the migrations directory — a crafted
    ``../`` segment cannot escape it (defense in depth; WO-GATE-HARDEN-CLEANUP).
    """
    import re

    source_root = Path(source_root)
    migrations_dir = (source_root / "core" / "event_store" / "migrations").resolve()
    found: list[Path] = []
    for match in re.finditer(r"core/event_store/migrations/(\S+\.sql)", git_diff):
        candidate = source_root / "core" / "event_store" / "migrations" / match.group(1)
        resolved = candidate.resolve()
        if not resolved.is_relative_to(migrations_dir):
            continue
        if resolved.is_file() and resolved not in found:
            found.append(resolved)
    return found


# ── Parallel grader execution ───────────────────────────────────────────────────


def _spawn_grader(prompt: str) -> subprocess.Popen:  # type: ignore[type-arg]
    """Spawn a grader, feeding the prompt via stdin.

    The prompt must NOT be passed as an argv element: with a real diff it
    routinely exceeds Windows' ~32K command-line limit and CreateProcess fails
    with WinError 206 (found re-verifying WO-DEBT-I under WO-GRADER-LOOKUP).
    Stdin is written from a daemon thread so all graders start consuming
    immediately and in parallel — a 64K pipe buffer would otherwise block the
    spawn loop on large prompts.
    """
    import threading

    proc = subprocess.Popen(
        ["claude", "--print"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    def _feed() -> None:
        try:
            assert proc.stdin is not None
            proc.stdin.write(prompt)
            proc.stdin.close()
        except Exception:
            pass  # broken pipe → grader died; _collect_grader surfaces it

    feeder = threading.Thread(target=_feed, daemon=True)
    feeder.start()
    # _collect_grader joins this before communicate() — communicate() closes
    # stdin, which would otherwise race a still-writing feeder and silently
    # truncate the prompt.
    proc._ds_feeder = feeder  # type: ignore[attr-defined]
    return proc


def _extract_first_json_object(text: str) -> "str | None":
    """Return the first balanced top-level JSON object substring, or None."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]  # noqa: E203
    return None


def _collect_grader(proc: subprocess.Popen, timeout: int = 360) -> dict[str, Any]:  # type: ignore[type-arg]
    try:
        feeder = getattr(proc, "_ds_feeder", None)
        if feeder is not None:
            feeder.join(timeout=120)
        stdout, _ = proc.communicate(timeout=timeout)
        output = stdout.strip()
        # T1: empty/whitespace-only output → unreviewable, not a hard failure.
        # Graders sometimes return nothing when the model is busy or the prompt
        # is truncated — treat as unreviewable so close_work_order is not blocked.
        if not output:
            return {"unreviewable": True, "reason": "grader_no_summary"}
        # Strip leading/trailing fences when the entire output is a fenced block.
        if output.startswith("```"):
            lines = output.splitlines()
            output = "\n".join(ln for ln in lines if not ln.strip().startswith("```")).strip()
        # Fast path: clean JSON.
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            pass
        # Slow path: prose prefix or trailing text — extract first balanced object.
        candidate = _extract_first_json_object(output)
        if candidate is not None:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
        raise ValueError(f"Grader returned non-JSON.\nRaw:\n{stdout[:500]}")
    except ValueError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Grader failed: {exc}")


def _run_graders_parallel(
    prompts: dict[str, str],
) -> dict[str, dict[str, Any]]:
    """Spawn all graders in parallel via Popen, collect results."""
    if os.environ.get(_MOCK_ENV):
        mocks: dict[str, dict[str, Any]] = {
            "completion": _MOCK_COMPLETION.copy(),
            "correctness": _MOCK_CORRECTNESS.copy(),
            "quality": _MOCK_QUALITY.copy(),
        }
        if "migration" in prompts:
            mocks["migration"] = _MOCK_MIGRATION.copy()
        return mocks

    procs = {name: _spawn_grader(prompt) for name, prompt in prompts.items()}
    results: dict[str, dict[str, Any]] = {}
    for name, proc in procs.items():
        try:
            result = _collect_grader(proc)
        except Exception as exc:
            # Grader failure is non-fatal; return a safe default so the rest proceeds.
            result = {"_grader_error": str(exc)}
        # T2: retry once on unreviewable (empty LLM output). Short timeout so
        # retries add at most ~30s to the close path.
        if result.get("unreviewable") and not result.get("_grader_error"):
            try:
                retry_proc = _spawn_grader(prompts[name])
                retry_result = _collect_grader(retry_proc, timeout=30)
                if not retry_result.get("unreviewable"):
                    result = retry_result
            except Exception:
                pass  # keep original unreviewable on retry failure
        results[name] = result
    return results


# ── Gap generation helpers ──────────────────────────────────────────────────────


def _violations_to_gaps(
    violations: list[dict[str, Any]],
    coverage_gaps: list[dict[str, Any]],
    migration_gaps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
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


# ── Score computation ───────────────────────────────────────────────────────────


def _compute_scores(
    completion: dict[str, Any],
    correctness: dict[str, Any],
    quality: dict[str, Any],
    total_tasks: int,
) -> dict[str, float]:
    # Completion score — grader may return it directly or we compute from tasks_verified.
    raw_completion = completion.get("completion_score")
    if raw_completion is not None:
        completion_score = float(raw_completion)
    elif total_tasks > 0:
        tasks_passed = sum(
            1 for t in completion.get("tasks_verified", []) if t.get("verdict") == "pass"
        )
        completion_score = tasks_passed / total_tasks
    else:
        completion_score = 1.0 if completion.get("passed", True) else 0.0

    # Correctness score.
    raw_correctness = correctness.get("correctness_score")
    if raw_correctness is not None:
        correctness_score = float(raw_correctness)
    else:
        violations = correctness.get("violations", [])
        correctness_score = max(0.0, 1.0 - len(violations) / 7.0) if violations else 1.0

    # Quality score — returned directly by grader.
    quality_score = float(quality.get("quality_score", 1.0))

    composite = (completion_score * 0.5) + (correctness_score * 0.3) + (quality_score * 0.2)

    return {
        "completion_score": round(completion_score, 4),
        "correctness_score": round(correctness_score, 4),
        "quality_score": round(quality_score, 4),
        "composite_score": round(composite, 4),
    }


# ── ds_eval_runs persistence ────────────────────────────────────────────────────


def _write_eval_run(
    conn: Any,
    *,
    work_order_id: str,
    scores: dict[str, float],
    passed: bool,
    failure_reasons: list[str],
    started_at: str,
    completed_at: str,
) -> None:
    try:
        run_id = str(uuid.uuid4())
        eval_id = f"work_order_verify:{work_order_id[:8]}"
        conn.execute(
            "INSERT INTO ds_eval_runs"
            " (run_id, eval_id, started_at, completed_at,"
            "  event_score, behavior_score, total_score, passed, failure_reasons)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                eval_id,
                started_at,
                completed_at,
                scores["completion_score"],
                scores["correctness_score"],
                scores["composite_score"],
                1 if passed else 0,
                json.dumps(failure_reasons),
            ),
        )
    except Exception:
        # ds_eval_runs may not exist in all environments; non-fatal.
        pass


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


def _gap_key(reviewed_work_order_id: str, gap: dict[str, Any]) -> str:
    """Stable dedup key for a spawned gap: (reviewed WO id + gap category).

    Stored as a ``[gap-key: ...]`` marker on the spawned WO's description so later
    re-reviews recognize prior spawns regardless of title phrasing (T1).
    """
    return f"{reviewed_work_order_id}::{_gap_category(gap)}"


def _gap_key_marker(gap_key: str) -> str:
    return f"[gap-key: {gap_key}]"


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
) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
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
        gap_key = _gap_key(reviewed_work_order_id, gap)
        marker = _gap_key_marker(gap_key)

        # Dedup on the stable gap key, NOT the free-text title, scoped by project_id
        # so null-milestone gaps still dedup (T3). Match across ANY status so a closed
        # prior spawn is never re-spawned (T4 respawn cap). Prefer an open WO so we can
        # merge tasks into it; a closed match means skip-and-log.
        existing_row = conn.execute(
            "SELECT work_order_id, status FROM business_work_orders"
            " WHERE project_id = ? AND instr(description, ?) > 0"
            " ORDER BY CASE status"
            "   WHEN 'in_progress' THEN 0 WHEN 'created' THEN 1 ELSE 2 END"
            " LIMIT 1",
            (project_id, marker),
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
            for task in gap.get("tasks", []):
                task_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO business_tasks"
                    " (task_id, work_order_id, project_id, title, description,"
                    "  status, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
                    (
                        task_id,
                        target_wo_id,
                        project_id,
                        task.get("title", ""),
                        task.get("description", ""),
                        now,
                        now,
                    ),
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


# ── Main entry point ────────────────────────────────────────────────────────────


def verify_work_order(
    *,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
    planning_root: Path | None = None,
) -> dict[str, Any]:
    """Run parallel independent verification for a work order.

    Returns::

        {
            "ok": bool,
            "work_order_id": str,
            "passed": bool,
            "summary": str,
            "completion": {...},        # grader 1 result
            "correctness": {...},       # grader 2 result
            "quality": {...},           # grader 3 result
            "migration": {...} | None,  # grader 4 result (migration-class only)
            "scores": {
                "completion_score": float,
                "correctness_score": float,
                "quality_score": float,
                "composite_score": float,
            },
            "gaps": [...],              # all combined gaps
            "spawned_work_orders": [...],
            "verdict_path": str,
            "auto_continue_warning": str | None,
        }
    """
    started_at = datetime.now(timezone.utc).isoformat()
    p_root = planning_root or Path.cwd() / ".planning"
    db_path = _require_db(source_root, dream_studio_home)

    with _connect(db_path) as conn:
        wo = _read_work_order(conn, work_order_id)
        if wo is None:
            return {"ok": False, "error": f"Work order not found: {work_order_id}"}

        tasks = _read_tasks(conn, work_order_id)
        if not tasks:
            return {"ok": False, "error": f"No tasks found for work order: {work_order_id}"}

        sql_check_results = _run_sql_checks(tasks, db_path)

        task_list_str = "\n".join(
            "{n}. [{st}] {title}: {desc}{ac}{sql}".format(
                n=i + 1,
                st=t["status"],
                title=t["title"],
                desc=t["description"],
                ac=(
                    f"\n   Acceptance criteria: {t['acceptance_criteria']}"
                    if t.get("acceptance_criteria")
                    else ""
                ),
                sql=_format_sql_checks(sql_check_results.get(t["title"], [])),
            )
            for i, t in enumerate(tasks)
        )
        git_diff = _collect_git_commits(source_root, work_order_id, title=wo["title"])

        # Unreviewable: no commit evidence by UUID or title token. Do NOT grade —
        # graders given an empty diff return score-0 "N/A: empty diff" violations
        # that spawn unactionable remediation WOs (WO-GRADER-LOOKUP). Record an
        # unreviewable verdict with a warning instead. Mock mode skips this so CI
        # fixtures (seeded WOs with no commits) keep exercising the grader path.
        if git_diff is None and not os.environ.get(_MOCK_ENV):
            token = wo["title"].split(" - ")[0].strip()
            warning = (
                f"independent review unreviewable: no commits found referencing "
                f"{work_order_id[:8]} or '{token}'. Work is NOT certified — review manually."
            )
            scores = {
                "completion_score": 0.0,
                "correctness_score": 0.0,
                "quality_score": 0.0,
                "composite_score": 0.0,
            }
            completed_at = datetime.now(timezone.utc).isoformat()
            _write_eval_run(
                conn,
                work_order_id=work_order_id,
                scores=scores,
                passed=False,
                failure_reasons=["unreviewable_no_commits_found"],
                started_at=started_at,
                completed_at=completed_at,
            )
            verdict_dir = p_root / "work-orders" / work_order_id
            verdict_dir.mkdir(parents=True, exist_ok=True)
            verdict_path = verdict_dir / "review-verdict.json"
            verdict_path.write_text(
                json.dumps(
                    {
                        "work_order_id": work_order_id,
                        "passed": False,
                        "unreviewable": True,
                        "unreviewable_reason": warning,
                        "scores": scores,
                        "auto_continue_warning": warning,
                        "completion": {},
                        "correctness": {},
                        "quality": {},
                        "gaps": [],
                        "spawned_work_orders": [],
                        "verified_at": completed_at,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            return {
                "ok": True,
                "work_order_id": work_order_id,
                "passed": False,
                "unreviewable": True,
                "summary": warning,
                "completion": {},
                "correctness": {},
                "quality": {},
                "migration": None,
                "scores": scores,
                "auto_continue_warning": warning,
                "gaps": [],
                "spawned_work_orders": [],
                "verdict_path": str(verdict_path),
            }
        if git_diff is None:
            git_diff = f"(no commits found referencing {work_order_id[:8]})"

        # Build grader prompts.
        prompts: dict[str, str] = {
            "completion": _COMPLETION_PROMPT_TEMPLATE.format(
                title=wo["title"],
                work_order_id=work_order_id,
                work_order_type=wo.get("work_order_type", "infrastructure"),
                task_list=task_list_str,
                git_diff=git_diff,
            ),
            "correctness": _CORRECTNESS_PROMPT_TEMPLATE.format(git_diff=git_diff),
            "quality": _QUALITY_PROMPT_TEMPLATE.format(git_diff=git_diff),
        }

        # Grader 4: migration — only when diff includes migration SQL files.
        migration_files = _find_migration_files(source_root, git_diff)
        if migration_files:
            mf = migration_files[0]
            try:
                migration_sql = mf.read_text(encoding="utf-8")
            except Exception:
                migration_sql = "(could not read migration file)"
            prompts["migration"] = _MIGRATION_PROMPT_TEMPLATE.format(
                migration_file=mf.name,
                migration_sql=migration_sql,
            )

        # Run all graders in parallel.
        grader_results = _run_graders_parallel(prompts)

        completion = grader_results.get("completion", _MOCK_COMPLETION.copy())
        correctness = grader_results.get("correctness", _MOCK_CORRECTNESS.copy())
        quality = grader_results.get("quality", _MOCK_QUALITY.copy())
        migration: dict[str, Any] | None = grader_results.get("migration")

        # T1/T3: Detect unreviewable graders (empty LLM output after retry).
        # Record and surface a warning instead of scoring — there is nothing to
        # remediate and spawning gap WOs for an empty diff would be unactionable.
        # Mock mode bypasses this so CI fixtures keep exercising the grader path.
        unreviewable_graders = [
            name
            for name in ("completion", "correctness", "quality", "migration")
            if name in grader_results and grader_results[name].get("unreviewable")
        ]
        if unreviewable_graders and not os.environ.get(_MOCK_ENV):
            reason_str = ", ".join(unreviewable_graders)
            warning = (
                f"independent review unreviewable: grader(s) [{reason_str}] returned empty output. "
                f"Work is NOT certified — review manually."
            )
            scores = {
                "completion_score": 0.0,
                "correctness_score": 0.0,
                "quality_score": 0.0,
                "composite_score": 0.0,
            }
            completed_at = datetime.now(timezone.utc).isoformat()
            _write_eval_run(
                conn,
                work_order_id=work_order_id,
                scores=scores,
                passed=False,
                failure_reasons=["unreviewable_grader_no_summary"],
                started_at=started_at,
                completed_at=completed_at,
            )
            verdict_dir = p_root / "work-orders" / work_order_id
            verdict_dir.mkdir(parents=True, exist_ok=True)
            verdict_path = verdict_dir / "review-verdict.json"
            verdict_path.write_text(
                json.dumps(
                    {
                        "work_order_id": work_order_id,
                        "passed": False,
                        "unreviewable": True,
                        "unreviewable_graders": unreviewable_graders,
                        "unreviewable_reason": warning,
                        "scores": scores,
                        "auto_continue_warning": warning,
                        "completion": completion,
                        "correctness": correctness,
                        "quality": quality,
                        "gaps": [],
                        "spawned_work_orders": [],
                        "verified_at": completed_at,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            return {
                "ok": True,
                "work_order_id": work_order_id,
                "passed": False,
                "unreviewable": True,
                "unreviewable_graders": unreviewable_graders,
                "summary": warning,
                "completion": completion,
                "correctness": correctness,
                "quality": quality,
                "migration": migration,
                "scores": scores,
                "auto_continue_warning": warning,
                "gaps": [],
                "spawned_work_orders": [],
                "verdict_path": str(verdict_path),
            }

        # Compute scores.
        scores = _compute_scores(completion, correctness, quality, total_tasks=len(tasks))
        composite = scores["composite_score"]

        # Determine individual pass/fail signals.
        completion_passed = completion.get("passed", False)
        correctness_passed = correctness.get("correctness_passed", True)
        migration_safe = migration.get("migration_safe", True) if migration else True

        # Collect all gaps from all graders.
        all_gaps: list[dict[str, Any]] = []
        all_gaps.extend(completion.get("gaps", []))

        if not correctness_passed:
            all_gaps.extend(
                _violations_to_gaps(
                    correctness.get("violations", []),
                    correctness.get("coverage_gaps", []),
                    correctness.get("migration_gaps", []),
                )
            )

        if composite < 0.70:
            quality_errors = [i for i in quality.get("issues", []) if i.get("severity") == "error"]
            all_gaps.extend(_quality_issues_to_gaps(quality_errors))

        if migration and not migration_safe:
            all_gaps.extend(_migration_risks_to_gaps(migration.get("risks", [])))

        # Overall pass/fail.
        passed = completion_passed and correctness_passed and composite >= 0.70 and migration_safe

        auto_continue_warning: str | None = None
        if passed and composite < 0.85:
            auto_continue_warning = (
                f"Quality warning: composite score {composite:.2f} is below 0.85. "
                "Auto-continuing but recommend addressing quality issues."
            )

        # Collect failure reasons for eval_runs.
        failure_reasons: list[str] = []
        if not completion_passed:
            failure_reasons.append(f"completion_failed (score={scores['completion_score']:.2f})")
        if not correctness_passed:
            failure_reasons.append(f"correctness_failed (score={scores['correctness_score']:.2f})")
        if composite < 0.70:
            failure_reasons.append(f"composite_below_threshold ({composite:.2f} < 0.70)")
        if not migration_safe:
            failure_reasons.append("migration_unsafe")

        # T2: reject gaps that invent a numeric threshold absent from the AC text.
        acceptance_text = " ".join(
            f"{t.get('title', '')} {t.get('description', '')} {t.get('acceptance_criteria', '')}"
            for t in tasks
        )
        all_gaps = _filter_invented_threshold_gaps(all_gaps, acceptance_text)

        # Register gap WOs. milestone_id is no longer required (T3): null-milestone
        # gaps still spawn and dedup, scoped by project_id.
        spawned: list[dict[str, Any]] = []
        if all_gaps and wo.get("project_id"):
            spawned = _insert_gap_work_orders(
                conn,
                gaps=all_gaps,
                project_id=wo["project_id"],
                milestone_id=wo.get("milestone_id"),
                reviewed_work_order_id=work_order_id,
                reviewed_wo_title=wo["title"],
                reviewed_wo_sequence=wo.get("sequence_order"),
            )

        completed_at = datetime.now(timezone.utc).isoformat()

        # Write eval run.
        _write_eval_run(
            conn,
            work_order_id=work_order_id,
            scores=scores,
            passed=passed,
            failure_reasons=failure_reasons,
            started_at=started_at,
            completed_at=completed_at,
        )

        # Write verdict JSON.
        verdict_dir = p_root / "work-orders" / work_order_id
        verdict_dir.mkdir(parents=True, exist_ok=True)
        verdict_path = verdict_dir / "review-verdict.json"
        full_verdict: dict[str, Any] = {
            "work_order_id": work_order_id,
            "passed": passed,
            "scores": scores,
            "auto_continue_warning": auto_continue_warning,
            "completion": completion,
            "correctness": correctness,
            "quality": quality,
            "gaps": all_gaps,
            "spawned_work_orders": spawned,
            "verified_at": completed_at,
        }
        if migration is not None:
            full_verdict["migration"] = migration
        verdict_path.write_text(json.dumps(full_verdict, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "work_order_id": work_order_id,
        "passed": passed,
        "summary": completion.get("summary", ""),
        "completion": completion,
        "correctness": correctness,
        "quality": quality,
        "migration": migration,
        "scores": scores,
        "auto_continue_warning": auto_continue_warning,
        "gaps": all_gaps,
        "spawned_work_orders": spawned,
        "verdict_path": str(verdict_path),
    }
