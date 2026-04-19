# Plan: Multi-Perspective Analysis Skill (`analyze`)

Spec: `.planning/analyze-skill.md`
Date: 2026-04-18

## Tasks

### 1. Create modes.yml with all 3 modes and resilience fields
- Files: `skills/analyze/modes.yml`
- Depends on: none
- Acceptance: File exists with `evaluate-offer`, `evaluate-gig`, `evaluate-data` modes. Each mode has `analysts`, `quick_analysts`, `max_parallel`, `min_quorum`, `raw_input`, `always_synthesize`, and `synthesis` (strategy, disagreement_threshold, output). YAML parses without error.

### 2. Create evaluate-offer analyst YAMLs (4 files)
- Files: `skills/analyze/analysts/compensation.yml`, `growth.yml`, `risk.yml`, `lifestyle.yml`
- Depends on: none
- Acceptance: Each file has required fields: `name`, `perspective`, `weight` (1.0), `model`, `signal_scale`, `prompt_template`. Prompt templates use `{{name}}`, `{{perspective}}`, `{{input}}` placeholders. Templates instruct analyst to return JSON with `signal`, `confidence`, `reasoning`, `key_factors`.

### 3. Create evaluate-gig analyst YAMLs (4 files)
- Files: `skills/analyze/analysts/profitability.yml`, `feasibility.yml`, `scope-risk.yml`, `timeline.yml`
- Depends on: none
- Acceptance: Same field requirements as Task 2. Each analyst has a distinct perspective relevant to freelance/consulting assessment.

### 4. Create evaluate-data analyst YAMLs (4 files)
- Files: `skills/analyze/analysts/anomaly.yml`, `trend.yml`, `hypothesis.yml`, `validation.yml`
- Depends on: none
- Acceptance: Same field requirements as Task 2. Each analyst has a distinct perspective relevant to dataset/BI analysis.

### 5. Create feed schema (analyze.schema.json)
- Files: `~/.dream-studio/feeds/analyze.schema.json`
- Depends on: none
- Acceptance: Valid JSON Schema (draft 2020-12). Defines `schema_version` (const 1), `last_updated`, `analyses_completed`, `last_analysis` (mode, topic, recommendation, confidence, contested_dimensions, report_path, timestamp), `in_progress` (nullable object with mode, topic, analysts_completed, analysts_total, started_at). Follows career-ops.schema.json conventions.

### 6. Create initial feed JSON (analyze.json)
- Files: `~/.dream-studio/feeds/analyze.json`
- Depends on: 5
- Acceptance: Valid JSON matching the schema. All fields at zero/null initial state. Matches the pattern of career-ops.json (empty but structurally complete).

### 7. Create analyze directory and empty checkpoint
- Files: `~/.dream-studio/analyze/checkpoint.json`
- Depends on: none
- Acceptance: Directory `~/.dream-studio/analyze/` exists. `checkpoint.json` contains `{"schema_version": 1, "status": "idle"}` as base state. Directory `~/.dream-studio/analyze/reports/` exists.

### 8. Write SKILL.md — frontmatter + trigger + purpose + signal scale reference
- Files: `skills/analyze/SKILL.md`
- Depends on: none
- Acceptance: Frontmatter has `name: analyze`, `description` with trigger patterns, `user_invocable: true`, `args: mode`, `argument-hint` listing all 3 modes + `--quick`. Body has Trigger, Purpose, and Signal Scale sections. Does NOT yet contain orchestration logic (that's Task 9).

### 9. Write SKILL.md — orchestration logic (validation gate + input summary + analyst dispatch)
- Files: `skills/analyze/SKILL.md` (append to Task 8)
- Depends on: 1, 2, 3, 4, 8
- Acceptance: SKILL.md contains complete orchestration instructions covering:
  - **BP1 gate:** Validate modes.yml exists, mode is defined, all analyst YAMLs exist with required fields. Fail fast with specific error if any missing.
  - **BP9 guard:** Check checkpoint status. If `analyzing`, ask user to resume/restart/wait.
  - **BP8 summary:** If mode has `raw_input: false`, create structured input summary before dispatch.
  - **BP5 resume:** If checkpoint has completed analysts with matching input_hash, skip them.
  - **Dispatch:** Read analyst YAMLs, substitute `{{placeholders}}`, spawn subagents in waves of `max_parallel`. Each analyst returns structured JSON signal.
  - **BP3 validation:** Validate each signal (valid signal value, confidence 0-1, non-empty reasoning). One retry if malformed, then treat as missing.
  - **BP2 quorum:** After all waves complete, check `min_quorum`. If not met, save checkpoint and stop with report.
  - **Checkpoint write:** Save all completed signals, update status to `synthesizing`. Use temp-file-then-rename.

### 10. Write SKILL.md — mechanical scoring + synthesis dispatch + output
- Files: `skills/analyze/SKILL.md` (append to Task 9)
- Depends on: 9
- Acceptance: SKILL.md contains complete instructions for:
  - **Mechanical scoring:** Map signals to [-2, -1, 0, 1, 2]. Compute per-analyst weighted score (numeric × confidence × weight). Compute aggregate weighted average. Flag disagreements where signal distance > `disagreement_threshold`.
  - **BP4 short-circuit:** If all analysts agree within 1 level and confidence > 0.7 and `always_synthesize` is false, generate brief mechanical memo inline. Skip synthesis subagent.
  - **Synthesis dispatch:** Spawn sonnet subagent with: all signals as structured JSON, mechanical scores table, contested dimensions list, mode-specific output template. Synthesis must: give final recommendation (signal + confidence), address each contested dimension, list key trade-offs, list action items.
  - **BP6 guards:** Post-check synthesis matches actual signals. Retry if hallucinated. Retry if missing sections. Fallback to raw signals + mechanical score if second failure.
  - **Report write:** Write markdown memo to `~/.dream-studio/analyze/reports/<mode>-<topic>-<date>.md`.
  - **Checkpoint update:** Status → `complete`, set `report_path`.
  - **Feed update:** Update `~/.dream-studio/feeds/analyze.json` with analysis result. Validate against schema before write.
  - **Present:** Show decision memo to user.

### 11. Write SKILL.md — resume logic + quick mode + anti-patterns
- Files: `skills/analyze/SKILL.md` (append to Task 10)
- Depends on: 10
- Acceptance: SKILL.md contains:
  - **Resume section:** Full instructions for resuming from checkpoint (load checkpoint, verify input_hash, skip completed analysts, run pending, continue to synthesis).
  - **Quick mode:** When `--quick` flag is passed, use `quick_analysts` list instead of full `analysts` list. Quorum adjusts to `min(min_quorum, len(quick_analysts))`.
  - **User extensibility section:** Instructions for adding custom analysts (create YAML, add to modes.yml) and custom modes.
  - **Anti-patterns:** List of things not to do (skip validation gate, ignore quorum, proceed with unfixed synthesis errors, dispatch parallel analysts to same context, skip checkpoint writes).
  - **Next in pipeline:** Where this skill fits (standalone or after career-evaluate).

### 12. Integration test — dry run with evaluate-offer mode
- Files: none (verification only)
- Depends on: 1, 2, 6, 7, 9, 10, 11
- Acceptance: Invoke `/analyze evaluate-offer` with a sample job offer. Verify: (a) validation gate passes, (b) 4 analyst subagents spawn in waves of 2, (c) each returns valid structured signal, (d) mechanical scores compute correctly, (e) synthesis subagent produces decision memo with all required sections, (f) checkpoint.json shows status `complete`, (g) analyze.json feed is updated, (h) report markdown exists at expected path.

## Dependency Graph

```
Wave 1 (parallel, no deps):
  Task 1: modes.yml
  Task 2: evaluate-offer analysts (4 YAMLs)
  Task 3: evaluate-gig analysts (4 YAMLs)
  Task 4: evaluate-data analysts (4 YAMLs)
  Task 5: feed schema
  Task 7: analyze dir + checkpoint
  Task 8: SKILL.md frontmatter

Wave 2 (depends on Wave 1):
  Task 6: initial feed JSON (needs 5)
  Task 9: SKILL.md orchestration (needs 1, 2, 3, 4, 8)

Wave 3 (sequential):
  Task 10: SKILL.md scoring + synthesis (needs 9)

Wave 4 (sequential):
  Task 11: SKILL.md resume + quick + anti-patterns (needs 10)

Wave 5 (verification):
  Task 12: Integration test (needs all)
```

## Summary

| # | Task | Depends on | Complexity | Files |
|---|---|---|---|---|
| 1 | modes.yml | none | low | 1 new |
| 2 | evaluate-offer analysts | none | medium | 4 new |
| 3 | evaluate-gig analysts | none | medium | 4 new |
| 4 | evaluate-data analysts | none | medium | 4 new |
| 5 | feed schema | none | low | 1 new |
| 6 | initial feed JSON | 5 | low | 1 new |
| 7 | analyze dir + checkpoint | none | low | 2 new |
| 8 | SKILL.md frontmatter | none | low | 1 new |
| 9 | SKILL.md orchestration | 1,2,3,4,8 | high | edit |
| 10 | SKILL.md scoring + synthesis | 9 | high | edit |
| 11 | SKILL.md resume + extras | 10 | medium | edit |
| 12 | Integration test | all | medium | none |

**Total: 18 new files + 1 SKILL.md built incrementally across 3 tasks. 5 waves.**
