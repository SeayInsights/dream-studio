# Behavioral Eval Authoring Guide

**18.8.3 — Behavioral Eval Harness**

This guide explains how to write a behavioral eval case for Dream Studio. Behavioral evals test *session-level correctness* — did Claude follow the skill's instructions correctly? They are not unit tests and not static rule detection.

## Quick Start

1. Create a JSON file in `evals/` following `schemas/behavioral_eval.schema.json`.
2. Give it a stable snake_case `eval_id` (no spaces, lowercase, underscore-separated).
3. Run with: `ds eval run --eval-id <your_eval_id>`

## Schema Reference

```json
{
  "eval_id": "eval_11_my_new_eval",
  "version": "1.0.0",
  "description": "One sentence: what session behavior is under test.",
  "skill_id": "ds-project",
  "input_prompt": "The user message that starts the session.",
  "fixture_events": [...],
  "expected_events": [...],
  "expected_behavior": "1-2 sentences describing expected session outcome.",
  "negative_checks": ["Claude must not do X"],
  "event_weight": 0.7,
  "behavior_weight": 0.3,
  "minimum_score": 0.75
}
```

Full schema: `schemas/behavioral_eval.schema.json`.

## The Two Scoring Halves

### Event score (70% weight — deterministic)

List events that must appear or must NOT appear in the session event log.

```json
"expected_events": [
  {"event_type": "skill.invoked", "skill_id": "ds-project:resume", "must_appear": true},
  {"event_type": "code.generated", "must_appear": false}
]
```

Rules:
- `must_appear: true` — event must be present. Missing → score 0 for that check.
- `must_appear: false` — event must NOT be present (negative check). Present → score penalty.
- `skill_id` is optional; if set, the event must also match on `trace.skill_id`.
- `max_sequence_position` (optional int) — if set, event must appear at or before that index.

**Prefer event checks over behavior text checks.** Events are deterministic; behavior text is probabilistic.

### Behavior score (30% weight — LLM-judged)

`expected_behavior` is 1-2 sentences graded by an Opus judge.

```json
"expected_behavior": "Claude invokes the resume skill and presents the active work order."
```

**Keep it short.** Opus judge reliability drops as behavior text grows. One clear assertion beats three ambiguous ones.

`negative_checks` is a list of plain-English assertions that must NOT be true:

```json
"negative_checks": ["Claude must not start writing code before checking project state"]
```

## Fixture Events (for unit tests)

`fixture_events` is a list of pre-seeded events injected into the runner without a live session. Use this for fast, deterministic local tests.

```json
"fixture_events": [
  {"event_type": "skill.invoked", "trace": {"skill_id": "ds-project:resume"}},
  {"event_type": "cli.command", "payload": {"command_pattern": "ds project state"}}
]
```

When `fixture_events` is provided, the runner uses them directly. This lets `ds eval run` work without a live Claude session.

## Scoring Model

| Component | Weight | Type |
|-----------|--------|------|
| Event score | 70% (default) | Deterministic — events present/absent |
| Behavior score | 30% (default) | LLM-judged (Opus) — transcript matches description |
| Composite | 100% | Weighted sum |
| Pass threshold | 0.75 (default) | Composite score ≥ this value → passed |

The runner executes each eval case with its `fixture_events`. For live sessions, it captures events from `canonical_events`/`ai_canonical_events` post-session.

## Regression Detection

Each eval run is compared against the stored baseline in `ds_eval_baselines`.

- Score drops > 10% vs baseline → flagged as regression.
- Baseline does NOT auto-update on regression — use `ds eval baseline` to print current baselines, then `core.eval.baseline.update_baseline()` for an explicit update.

## Naming Convention

```
eval_NN_short_description.json
```

- `NN` — two-digit sequence number (01–99).
- `short_description` — underscore-separated, describes the behavior tested.

Examples: `eval_01_event_sequence_skill_dispatch.json`, `eval_09_resume_after_break.json`.

## CI Integration

Two-tier CI:
- **PR push** — quick suite (evals 01–05) via `ds eval run --all` on the quick subset.
- **PR merge** — full suite (all evals) runs in the post-merge `full-ci.yml` workflow.

A regression > 5% vs baseline in the full suite blocks a future PR from merging.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Long `expected_behavior` text | Keep to 1-2 assertions; split complex behavior into multiple evals |
| Only behavior checks, no events | Always add at least 1 expected event (deterministic anchor) |
| `must_appear: false` on every event | Negative checks are expensive; use only for genuinely forbidden behaviors |
| Same `eval_id` as an existing file | Choose a unique ID; two files with the same `eval_id` cause test failures |
| Skipping `fixture_events` | Without fixture events, the unit tests can't run the eval deterministically |
