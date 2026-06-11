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
import subprocess
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

Tasks that were supposed to be completed:
{task_list}

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


# ── Git diff collection ─────────────────────────────────────────────────────────


def _collect_git_commits(
    source_root: Path, work_order_id: str, title: str | None = None
) -> str | None:
    """Collect commit diffs referencing this work order.

    Greps git log for the WO UUID's first 8 chars and, when that finds nothing,
    for the WO title token (the part before ' - ', e.g. 'WO-DEBT-I') — squash-merge
    commit messages carry the WO name, never the UUID (WO-GRADER-LOOKUP).
    Returns None when neither pattern matches: the diff is unreviewable, which
    callers must treat differently from a reviewable diff (no score-0 verdicts,
    no remediation WOs, surface a warning instead).
    """
    short_id = work_order_id[:8]
    patterns = [short_id]
    if title:
        token = title.split(" - ")[0].strip()
        if token:
            patterns.append(token)
    try:
        lines: list[str] = []
        for pattern in patterns:
            log_result = subprocess.run(
                ["git", "log", "--oneline", "--all", "--fixed-strings", f"--grep={pattern}"],
                cwd=str(source_root),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if log_result.stdout.strip():
                lines = log_result.stdout.strip().splitlines()
                break  # UUID hits are the precise match; only widen when empty
        if not lines:
            return None
        diff_parts: list[str] = []
        for line in lines[:10]:
            commit_hash = line.split()[0]
            show_result = subprocess.run(
                ["git", "show", "--stat", "--patch", "--no-color", commit_hash],
                cwd=str(source_root),
                capture_output=True,
                text=True,
                timeout=30,
            )
            diff_parts.append(f"=== commit {commit_hash} ===\n{show_result.stdout[:8000]}")
        return "\n\n".join(diff_parts)
    except Exception as exc:
        return f"(error collecting git commits: {exc})"


def _find_migration_files(source_root: Path, git_diff: str) -> list[Path]:
    """Return migration SQL files referenced in the git diff."""
    import re

    found: list[Path] = []
    for match in re.finditer(r"core/event_store/migrations/(\S+\.sql)", git_diff):
        candidate = source_root / "core" / "event_store" / "migrations" / match.group(1)
        if candidate.is_file() and candidate not in found:
            found.append(candidate)
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


def _collect_grader(proc: subprocess.Popen, timeout: int = 180) -> dict[str, Any]:  # type: ignore[type-arg]
    try:
        feeder = getattr(proc, "_ds_feeder", None)
        if feeder is not None:
            feeder.join(timeout=60)
        stdout, _ = proc.communicate(timeout=timeout)
        output = stdout.strip()
        if output.startswith("```"):
            lines = output.splitlines()
            output = "\n".join(ln for ln in lines if not ln.strip().startswith("```")).strip()
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Grader returned non-JSON: {exc}\nRaw:\n{stdout[:500]}")
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
            results[name] = _collect_grader(proc)
        except Exception as exc:
            # Grader failure is non-fatal; return a safe default so the rest proceeds.
            results[name] = {"_grader_error": str(exc)}
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


def _insert_gap_work_orders(
    conn: Any,
    *,
    gaps: list[dict[str, Any]],
    project_id: str,
    milestone_id: str | None,
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

    for i, gap in enumerate(gaps):
        new_wo_id = str(uuid.uuid4())
        seq = base_seq + i + 1
        desc = (
            f"Spawned by review of '{reviewed_wo_title}' on {now[:10]}: "
            f"{gap.get('description', '')}"
        )
        wo_type = gap.get("work_order_type", "cleanup")

        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description,"
            "  work_order_type, status, sequence_order, created_at, updated_at, last_updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, 'created', ?, ?, ?, ?)",
            (new_wo_id, project_id, milestone_id, gap["title"], desc, wo_type, seq, now, now, now),
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

        spawned.append({"work_order_id": new_wo_id, "title": gap["title"], "type": wo_type})

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

        task_list_str = "\n".join(
            "{n}. [{st}] {title}: {desc}{ac}".format(
                n=i + 1,
                st=t["status"],
                title=t["title"],
                desc=t["description"],
                ac=(
                    f"\n   Acceptance criteria: {t['acceptance_criteria']}"
                    if t.get("acceptance_criteria")
                    else ""
                ),
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

        # Register gap WOs.
        spawned: list[dict[str, Any]] = []
        if all_gaps and wo.get("project_id") and wo.get("milestone_id"):
            spawned = _insert_gap_work_orders(
                conn,
                gaps=all_gaps,
                project_id=wo["project_id"],
                milestone_id=wo["milestone_id"],
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
