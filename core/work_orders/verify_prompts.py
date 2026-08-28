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

WHERE THIS WORK IS HEADED (WO-MULTIROOT-REVIEW task 9). The diff under review is still
the only thing you are grading -- this is context for two judgements that are not
decidable from one diff alone. A mechanism that looks over-built for this work order
alone may be the shared piece a sibling needs, and "does it address the issue" often
means the MILESTONE's issue, not this work order's slice of it.
{direction_context}

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
Grade the diff below ONLY against the rules listed here.

WO-MULTIROOT-REVIEW tasks 5-6: these rules are RESOLVED, not hardcoded. Seven of the
eight rules that used to be baked into this template named Dream Studio files by path,
and every other project was graded against them -- which is why reviewing Fulcrum
produced nonsense. The baseline is now industry-standard SDLC practice, and a project or
folder may add to it or replace it.

Rules in force for this review ({rules_provenance}):
{rules_block}

Grade against THOSE rules and no others. Do not import rules from your own knowledge of
how a project "should" be laid out: if a boundary is not stated above, crossing it is not
a violation here.

A rule that does not apply to this diff is NOT a violation. Say nothing about it rather
than reporting an absence -- the reviewer's inability to check something is not the
author's defect, and it must never become scheduled work.

Git diff to review:
{git_diff}

Return ONLY valid JSON (no prose, no markdown fences):
{{
  "correctness_passed": <bool: true only if violations, coverage_gaps, and migration_gaps are ALL empty>,
  "correctness_score": <float 0.0-1.0: 1.0 if no violations, else max(0.0, 1.0 - violation_count / {rule_count})>,
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
(7) DURABLE-STATE ADVERSARIAL COVERAGE: when the diff introduces or modifies durable state that a read path trusts (a marker, a token or claim record, a cached row, a version stamp, a status flag another component reads), the diff must also carry an adversarial test for the failure window between the write and the read — crash mid-write, race between writers, version/schema skew between writer and reader. FLAG AS ERROR: a silent key mismatch where the persist path stores under one key/column/name and the read path looks up a DIFFERENT key/column/name (the write "succeeds", the reader finds nothing, no error surfaces anywhere). A diff adding trusted durable state with no crash/race/skew test is an error-severity finding; the test may live in the same diff under any name — judge by what it exercises, not its filename.
(8) CONFIG-AS-PROXY / SIGNAL-VS-REACHABILITY: a guard that gates a secret, token, credential, or privileged response on a CONFIG SIGNAL (a URL string, an env flag, a display value, a mode name) rather than on the property that actually controls reachability or validity (bind address, the requesting client's address, token audience/binding, actual network exposure) is an error-severity finding. Trace what the secret is valid AGAINST, not what the message displays: if a response returns a live credential/token, the condition guarding it must be the condition that makes it safe — flag any case where a different knob (e.g. BIND_HOST vs a base-URL default) can open the hole while the guard still believes it is closed.

Return ONLY valid JSON (no prose, no markdown fences):
{{
  "quality_passed": <bool: true if no error-severity issues>,
  "quality_score": <float 0.0-1.0: 1.0 if no issues, subtract 0.1 per error, 0.03 per warning, floor at 0.0>,
  "issues": [
    {{
      "category": "<rule name: SECURITY | ERROR_HANDLING | TYPE_SAFETY | API_DESIGN | TEST_QUALITY | SQL_PATTERNS | DURABLE_STATE_ADVERSARIAL | CONFIG_AS_PROXY>",
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

# ── Grader 5 — Falsification analyst (WO-FALSIFY-FIRST-PASS) ───────────────────
#
# The systemic answer to the 2026-08-18 audit: every other grader checks
# COMPLIANCE with criteria the author wrote. None asks "what should have been
# tested and wasn't" — the question a human reviewer asked across seven rounds
# of gw#619. This grader asks it by construction: it enumerates the worst
# reachable states for the change and must classify EVERY scenario it raises as
# COVERED / PROPOSED / UNVERIFIED. Nothing may be left silent; an untestable
# risk becomes a named UNVERIFIED ledger entry rather than an unknown.

_FALSIFICATION_PROMPT_TEMPLATE = """You are an adversarial falsification analyst.
Your job is NOT to confirm the change works. Your job is to enumerate the worst
reachable states this change permits, and to say — for each one — whether a test
actually covers it.

Work order: {title}
Task list:
{task_list}

Git diff to analyse:
{git_diff}

Scenario taxonomy. Consider EVERY class; skip a class only when it genuinely
cannot apply to this diff (do not pad with irrelevant scenarios):

(1) crash_mid_write — the process dies between a write and the read that trusts
    it. Durable state left half-written, a marker present without its payload.
(2) race_between_writers — two processes/sessions write the same state
    concurrently; last-write-wins clobber, lost update, interleaved partial rows.
(3) version_skew — writer and reader run different code/schema versions; a field
    added or renamed on one side only; a stale deployed copy of the same module.
(4) partial_failure — a multi-step operation succeeds partway (store A written,
    store B not), with no reconciliation to detect the split.
(5) malformed_input — hostile or corrupt input reaches a parser: truncated JSON,
    wrong types, unexpected encodings, paths with spaces/quotes/globs.
(6) interrupted_io — a file move, copy, or fsync interrupted; a lock held; a disk
    full; a network read cut mid-stream.
(7) reachability_vs_config — CRITICAL for anything returning a secret, token,
    credential, signed URL, or privileged response: identify what the value is
    actually VALID AGAINST (bind address, requesting client address, token
    audience/binding, real network exposure) versus what the code CHECKS (a URL
    string, an env flag, a mode name, a display value). Flag any case where a
    different knob can open the hole while the guard still believes it is closed.
(8) empty_absent_state — the happy path assumes rows/files/config exist; what
    happens on a fresh install, an empty table, a missing artifact, a first run.

For each scenario you raise, classify it:
  COVERED    — an existing test or check exercises it. Put the test node-id (or
               the specific check) in "evidence". Do not claim COVERED without
               naming the evidence.
  PROPOSED   — it is testable but no test exists. Put a concrete proposed test
               name plus the assertion it would make in "evidence".
  UNVERIFIED — it cannot be tested now (needs infrastructure, a second provider,
               a real deploy). Put WHY in "evidence".

Severity: "error" for a scenario that would corrupt durable state, leak a
credential, or silently lose data; "warning" for degraded behavior; "info" for
cosmetic or already-mitigated cases.

Return ONLY valid JSON (no prose, no markdown fences):
{{
  "falsification_score": <float 0.0-1.0: 1.0 when no scenario is UNVERIFIED and
      none is an error-severity PROPOSED; subtract 0.15 per error-severity
      PROPOSED, 0.10 per UNVERIFIED, 0.03 per warning-severity PROPOSED, floor 0.0>,
  "summary": "<one sentence: the worst reachable state and whether it is covered>",
  "scenarios": [
    {{
      "scenario_class": "crash_mid_write" | "race_between_writers" | "version_skew"
          | "partial_failure" | "malformed_input" | "interrupted_io"
          | "reachability_vs_config" | "empty_absent_state",
      "surface": "<file path and function/symbol the scenario targets>",
      "scenario": "<the concrete worst-case sequence, in one sentence>",
      "status": "COVERED" | "PROPOSED" | "UNVERIFIED",
      "evidence": "<test node-id | proposed test name + assertion | why unverifiable>",
      "severity": "error" | "warning" | "info"
    }}
  ]
}}
"""
