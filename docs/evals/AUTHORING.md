# Behavioral Eval Authoring Guide

**18.8.3 — Behavioral Eval Harness (WO-N2: deterministic scoring)**

Behavioral evals test session-level correctness: did Claude follow the skill's instructions? Scoring is 100% deterministic — event pattern matching against expected event sequences. No live Claude sessions, no LLM judge.

## Quick Start

1. Create a JSON file in `evals/` following `schemas/behavioral_eval.schema.json`.
2. Give it a stable snake_case `eval_id` (lowercase, underscore-separated).
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
  "notes": "Optional: human-readable description of expected behavior. Not scored.",
  "event_weight": 1.0,
  "minimum_score": 0.75
}
```

Full schema: `schemas/behavioral_eval.schema.json`.

## Event Scoring (100% weight — deterministic)

List events that must appear or must NOT appear in the session event log.

```json
"expected_events": [
  {"event_type": "skill.invoked", "skill_id": "ds-project:resume", "must_appear": true},
  {"event_type": "code.generated", "must_appear": false}
]
```

Rules:
- `must_appear: true` — event must be present. Missing → 0 credit for that check.
- `must_appear: false` — negative check: event must NOT appear. Present → -0.2 score penalty.
- `skill_id` (optional) — event must also match on `trace.skill_id` or `skill_id` field.
- `max_sequence_position` (optional int) — event must appear at or before this 0-based index. Late → 0.5 partial credit instead of 1.0.
- `payload_contains` (optional object) — event payload must contain these key/value pairs.

## Scoring Model

| Component | Weight | Type |
|-----------|--------|------|
| Event score | 100% | Deterministic — events present/absent |
| Pass threshold | 0.75 (default) | Event score ≥ this value → passed |

Score formula:
- `base_score = credits / total_required_events`
- `credits`: 1.0 per matched required event; 0.5 if event present but out of sequence
- `final_score = max(0.0, base_score - 0.2 × negative_violations)`

## Fixture Events (for unit tests)

`fixture_events` is a list of pre-seeded events used instead of a live session. Required for deterministic local testing.

```json
"fixture_events": [
  {"event_type": "skill.invoked", "trace": {"skill_id": "ds-project:resume"}},
  {"event_type": "cli.command", "payload": {"command_pattern": "ds project state"}}
]
```

When `fixture_events` is provided, the runner matches against them directly. No subprocess, no network, no API key required.

When `fixture_events` is null, the runner reads events from `business_canonical_events` / `ai_canonical_events` for a recorded live session.

## Regression Detection

Each eval run is compared against the stored baseline in `ds_eval_baselines`.

- Score drops > 10% vs baseline → flagged as regression.
- Baseline does NOT auto-update on regression — use `ds eval baseline` to view current baselines, then `core.eval.baseline.update_baseline()` for an explicit update.

## Naming Convention

```
eval_NN_short_description.json
```

- `NN` — two-digit sequence number (01–99).
- `short_description` — underscore-separated, describes the behavior tested.

Examples: `eval_01_event_sequence_skill_dispatch.json`, `eval_09_resume_after_break.json`.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Using `notes` as a scoring signal | `notes` is documentation only; add `expected_events` for what you want scored |
| No `fixture_events` | Without fixtures, unit tests cannot run the eval deterministically |
| Negative checks on every event | Use `must_appear: false` only for genuinely forbidden behaviors |
| Same `eval_id` as an existing file | Two files with the same `eval_id` cause test failures |
| `event_weight` not 1.0 | Always set `event_weight: 1.0`; scoring is 100% events |
| Omitting `minimum_score` | Default is 0.75; override only if the eval intentionally allows more failure |
