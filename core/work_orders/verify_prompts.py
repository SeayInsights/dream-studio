"""Grader prompt templates for independent work-order verification.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/verify.py``. Holds the four
LLM grader prompt templates (completion, correctness, quality, migration). No
logic changes — extracted verbatim from the original module.
"""

from __future__ import annotations

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
