# Pre-Phase-19 Baseline

**Captured:** 2026-06-03
**WO:** 18.10 (Pre-Phase-19 Baseline Capture)
**Git tag:** `pre-phase-19-baseline`
**Purpose:** Frozen reference point for Phase 19 adaptive learning. Phase 19 extensions
are validated against these baseline scores to confirm they improve or don't degrade
skill behavior (Decision 6: minimum 5 work orders for active status).

---

## Methodology

All measurements taken from the live `studio.db` after Phase 18 completion (18.9 agent
realignment fully closed). No code changes in this WO — pure measurement.

**Capture approach:** Direct SQL queries against `studio.db` + filesystem snapshot.
Assumed CLI commands (`ds dashboard --export`, `ds skill list --with-metrics`) did not
exist as of Phase 18 completion; SQL equivalents used (documented per-metric below).

---

## 1. Behavioral Eval Suite Baseline

**File:** [`../../core/eval/baseline.py`](../../core/eval/baseline.py) reads from `ds_eval_baselines`

**Label:** `pre_phase_19` (added via migration 094 / ALTER TABLE ADD COLUMN label)

| Eval Case | Baseline Score | Re-run Score | Status |
|-----------|---------------|-------------|--------|
| eval_01_event_sequence_skill_dispatch | 0.850 | 1.000 | PASS |
| eval_02_behavior_text_quality_response | 0.750 | 1.000 | PASS |
| eval_03_mixed_events_and_behavior | 0.850 | 1.000 | PASS |
| eval_04_negative_check_no_direct_code | 0.850 | 1.000 | PASS |
| eval_05_regression_detection | 0.850 | 1.000 | PASS |

**Note on score difference:** Baseline scores were established when the eval harness
used neutral 0.5 fallback for the behavior component (no LLM judge at capture time).
Re-run scores reflect Claude Code judge giving 1.0 for well-formed fixture transcripts.
Both represent "passing" behavior — the baseline threshold is 0.75, all scores exceed it.

**Phase 19 contract:** `SELECT * FROM ds_eval_baselines WHERE label = 'pre_phase_19'` returns
these 5 rows. Phase 19.5 retroactive validation computes:
`current_eval_score >= baseline_eval_score * 0.95` to approve extensions.

---

## 2. Skill Metadata Snapshot

**Directory:** [`../../baselines/pre_phase_19/canonical_skills/`](../../baselines/pre_phase_19/canonical_skills/)

**Count:** 66 `metadata.yml` files captured (all skill modes across quality, domains, analyze packs)

**Key skills captured:**
- 11 quality skills: security, code-quality, database, testing, types-deps, backend-api, frontend-ux, architecture, ops, database-compliance, pre-launch
- 9 promoted-from-agent skills: accessibility, devops, kubernetes, research, idea-validation, technical-writing, terraform, mobile, data-engineering
- All sub-mode directories included (audit/, build/ if present)

**Immutability:** Git-committed at `pre-phase-19-baseline` tag. Use
`git show pre-phase-19-baseline:baselines/pre_phase_19/canonical_skills/` to retrieve.

**Phase 19 use:** Phase 19 can diff current `metadata.yml` against snapshot to detect
if skill descriptions or status changed post-adaptation.

---

## 3. Attribution Coverage

**File:** [`../../baselines/pre_phase_19/attribution_coverage.json`](../../baselines/pre_phase_19/attribution_coverage.json)

**Methodology:** SQL query on `canonical_events`:
```sql
SELECT COUNT(*) FROM canonical_events
WHERE event_type = 'token.consumption.recorded'
  AND json_extract(trace, '$.skill_specifier') IS NOT NULL
```

| Metric | Value |
|--------|-------|
| Total token consumption events | 638 |
| Attributed (skill_specifier present) | 0 |
| Attribution coverage | 0.00% |

**Interpretation:** Phase 18 token attribution infrastructure was built (18.4.3) but the
trace-level skill_specifier propagation was not activated during the Phase 18 development
sessions. Attribution coverage of 0% is the correct baseline — Phase 19 should improve this
as skill invocations are tracked end-to-end through the attribution pipeline.

---

## 4. Skill Effectiveness Metrics

**File:** [`../../baselines/pre_phase_19/skill_effectiveness.json`](../../baselines/pre_phase_19/skill_effectiveness.json)

**Methodology:** SQL query on `raw_skill_telemetry`:
```sql
SELECT skill_name, COUNT(*) AS times_used,
       AVG(CASE WHEN success=1 THEN 1.0 ELSE 0.0 END) AS success_rate,
       AVG(input_tokens + output_tokens) AS avg_token_usage
FROM raw_skill_telemetry
GROUP BY skill_name ORDER BY times_used DESC
```

| Skill | Times Used | Success Rate | Avg Tokens |
|-------|-----------|-------------|------------|
| (from raw_skill_telemetry) | 1 skill tracked | Varies | Varies |

**Interpretation:** Only 1 skill appears in `raw_skill_telemetry` — this reflects that
Phase 18 development sessions did not consistently invoke skills through the telemetry
pipeline. Most skill work was done directly via Task tool and eval fixtures, not tracked
in raw_skill_telemetry. Phase 19 usage will populate this table with real effectiveness data.

**Phase 19 use:** After Phase 19 begins enriching skills, compare updated effectiveness
metrics against these baseline values. Any skill where `success_rate` drops is a regression candidate.

---

## 5. Intelligence Surfacing Hit Rate

**File:** [`../../baselines/pre_phase_19/intelligence_hit_rate.json`](../../baselines/pre_phase_19/intelligence_hit_rate.json)

**Methodology:** Count `canonical_events` matching intelligence/pattern/insight event types, past 30 days:
```sql
SELECT event_type, COUNT(*) FROM canonical_events
WHERE created_at >= datetime('now', '-30 days')
  AND (event_type LIKE '%intelligence%' OR event_type LIKE '%pattern%'
       OR event_type LIKE '%insight%' OR event_type LIKE '%surfac%')
GROUP BY event_type
```

| Metric | Value |
|--------|-------|
| Total events in past 30 days | 6,530 |
| Intelligence surfacing events | 0 |
| Hit rate | 0.00% |

**Interpretation:** The 18.4.4 intelligence surfacing integration is present but has not
generated observable surfacing events in the canonical event log during Phase 18 development.
The 0% baseline is correct — Phase 19 should produce measurable intelligence surfacing
as adaptive enrichment begins and the surfacing pipeline activates.

---

## Summary Table

| Component | Baseline Value | Source | Phase 19 Expected Direction |
|-----------|--------------|--------|---------------------------|
| Eval suite pass rate | 5/5 (100%) | ds_eval_baselines | Maintain ≥ 100% |
| Eval composite scores | 0.75–1.00 | ds_eval_baselines | Maintain ≥ 0.75 |
| Token attribution coverage | 0.00% | canonical_events | Increase |
| Skill telemetry coverage | 1 skill | raw_skill_telemetry | Increase |
| Intelligence hit rate | 0.00% | canonical_events | Increase |

---

## Phase 19 Gate Usage

**Decision 6:** Extensions require minimum 5 past work orders validated before `active` status.
This baseline provides the reference eval scores for that comparison:
`current_eval_score >= baseline_eval_score * 0.95` → extension is valid.

**Phase 19.5 retroactive validation:** Reads `ds_eval_baselines WHERE label = 'pre_phase_19'`
to compute `baseline_eval_score` for `ds_user_extensions` rows.

**Regression alert threshold:** If any eval score drops below `baseline * 0.90`, investigate
before allowing Phase 19 enrichment to continue.

---

## Reproducibility

To reproduce these measurements:

```bash
# Eval baseline
git checkout pre-phase-19-baseline
python -c "from core.eval.runner import EvalRunner; r=EvalRunner(); print(r.run_all())"

# Attribution coverage
python -c "
import sqlite3; from core.config.database import _default_db_path
conn=sqlite3.connect(str(_default_db_path()))
total=conn.execute(\"SELECT COUNT(*) FROM canonical_events WHERE event_type='token.consumption.recorded'\").fetchone()[0]
attr=conn.execute(\"SELECT COUNT(*) FROM canonical_events WHERE event_type='token.consumption.recorded' AND json_extract(trace,'\\$.skill_specifier') IS NOT NULL\").fetchone()[0]
print(f'{attr}/{total} = {attr/total*100:.2f}%' if total else '0/0')
"

# Skill snapshot diff
diff -r baselines/pre_phase_19/canonical_skills/ canonical/skills/ --include="metadata.yml"
```
