# Improvement Model — Phase 19 Gap/Learning Loop

**Last reviewed:** 2026-06-08 — WO-LEARN (cf6a8d97-08b3-403e-81c2-2c4228a541f7)

## What This Is

Dream Studio improves its skills over time by detecting operator friction patterns
and proposing targeted extensions. Improvements are layered extensions stored in
`ds_user_extensions` and applied at dispatch — **canonical SKILL.md files are never
modified**. This preserves the deterministic skill base while enabling personalized
adaptation.

---

## The Four-Phase Loop

```
 Session ends
     │
     ▼
[Phase 19.2] FrictionSignalHarvester.harvest()
     │  writes to: ds_friction_signals
     │  detects: dismissed_finding, partial_completion, pattern_gap
     ▼
[Phase 19.3] GapClassifier.classify_all()
     │  updates: ds_friction_signals (classified_as, classification_confidence)
     │  outputs: capability | personalization | onboarding
     ▼
[Phase 19.4] WorkflowPatternAnalyzer.analyze()          ← wired in WO-LEARN
     │  writes to: ds_workflow_pattern_signals
     │  detects: always_paired, post_completion, pre_close
     ▼
[Phase 19.5] RetroactiveValidator.increment_for_session()
     │  increments: ds_user_extensions.past_wo_count for experimental extensions
     │  auto-validates when past_wo_count ≥ 5 (Decision 6 threshold)
     ▼
 end_session() returns
```

All four phases are **non-blocking** — session close completes even if any phase
errors. Each phase uses its own connection (from `get_connection()`) and closes it
in a `finally` block.

---

## Operator-Gated Step: confirm_signal()

The loop is intentionally NOT fully automated. After GapClassifier classifies a
signal, an operator confirms it via:

```
ds learn review               # surface classified signals
ds learn confirm <signal_id>  # GapClassifier.confirm_signal() → ds_user_extensions row
```

`confirm_signal()` creates a `ds_user_extensions` row with `status='proposed'`. The
extension ID is linked back to the friction signal.

**Why this gate exists:** False positives in gap classification would cause spurious
extensions. The operator confirmation ensures the inferred gap is real before
resources are spent on synthesis.

---

## Extension Lifecycle

```
proposed → experimental → active
              ↑
              │  RetroactiveValidator auto-promotes after past_wo_count ≥ 5
              │  and current_eval_score ≥ baseline * 0.95
              │
              └─ user_confirmed_at required for active status
```

Extensions in `status='active'` are applied at dispatch by the expansion layer
(Phase 19.4 / Guided Expansion). They augment the skill's runtime context —
they never patch SKILL.md.

---

## Wiring in end_session()

Location: `core/event_store/studio_db.py` → `end_session()` (Phase 19 blocks)

Order is load-bearing:
1. FrictionSignalHarvester — capture raw signals
2. GapClassifier — classify what was captured this session
3. WorkflowPatternAnalyzer — detect co-occurrence patterns (cross-session, uses canonical_events)
4. RetroactiveValidator — increment experimental extension counters, trigger validation when threshold crossed

---

## reg_workflows Decision (WO-LEARN Task 3)

**Decision:** `reg_workflows` is retained as the workflow **catalog** (maps workflow IDs
to YAML paths, categories, and node counts). It is populated by `hydrate_registry.py`
and read by `get_workflows_by_category()`.

**`track_workflow_success`** (deleted in wave 8) is **not restored**. The equivalent
need — detecting whether workflow invocations are effective — is covered by
`ds_workflow_pattern_signals` (confidence scores over co-occurrence counts) and
`RetroactiveValidator` (eval score delta). These provide richer signal than a
binary success/failure flag.

`reg_workflows` ≠ `track_workflow_success` — they served different purposes:
- `reg_workflows`: static catalog of available workflows
- `track_workflow_success` (retired): runtime success signal per invocation

The workflow pattern analyzer uses `canonical_events` (skill.invoked + session
boundary events) directly — it does not require `reg_workflows` to function.

---

## record_learning_event() / record_skill_evaluation() (WO-LEARN Task 2)

Both functions remain callable for Shared Intelligence workflows but are **not
wired into end_session()**. They write to `learning_event_records` and
`skill_evaluation_runs` (SI subsystem) — distinct tables from the Phase 19
friction/gap pipeline.

**Superseded by Phase 19** for the learning signal path:
- `record_learning_event()` ← superseded by `FrictionSignalHarvester` + `GapClassifier`
- `record_skill_evaluation()` ← superseded by `RetroactiveValidator` eval scoring

The SI functions remain for explicit manual recording in SI workflows where
structured learning event records with full provenance are needed.

---

## Table Reference

| Table | Owned by | Purpose |
|-------|----------|---------|
| `ds_friction_signals` | FrictionSignalHarvester (write) + GapClassifier (update) | Raw friction + classification |
| `ds_workflow_pattern_signals` | WorkflowPatternAnalyzer | Skill co-occurrence patterns |
| `ds_user_extensions` | GapClassifier.confirm_signal() (write) + RetroactiveValidator (update) | Proposed/experimental/active extensions |
| `reg_workflows` | hydrate_registry.py | Workflow catalog |
| `learning_event_records` | record_learning_event() | SI subsystem — explicit learning records |
| `skill_evaluation_runs` | record_skill_evaluation() | SI subsystem — eval run records |

---

## Where Improvements Live

The improvement does NOT live in:
- `canonical/skills/*.md` — canonical, immutable
- `canonical/workflows/*.md` — canonical, immutable
- `~/.claude/skills/` — adapter projection, regenerated by `ds update`

The improvement lives in:
- `ds_user_extensions` (DB row, `status='active'`)
- Applied at dispatch by the Guided Expansion layer (Phase 19.4)
- Visible via `ds learn show <extension_id>`
