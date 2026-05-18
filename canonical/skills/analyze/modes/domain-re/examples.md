# domain-re — Detailed Reference

Extracted from SKILL.md to reduce context injection size.

## Signal Scale

| Signal | Meaning in RE context |
|--------|----------------------|
| strong-accept | Execute — clear deal, numbers work, no significant flags |
| accept | Proceed with noted conditions — favorable with manageable concerns |
| neutral | Insufficient data or balanced trade-offs — needs more information |
| reject | Pass or renegotiate — deal has significant structural problems |
| strong-reject | Hard pass — numbers don't work or unacceptable risk |

## Analyst Output Schema

Every analyst returns exactly this JSON:
```json
{
  "signal": "strong-accept|accept|neutral|reject|strong-reject",
  "confidence": 0.0-1.0,
  "reasoning": "2-3 sentences with institutional rigor — specific numbers, not vague assessments",
  "key_factors": [
    "specific quantified factor 1",
    "specific quantified factor 2",
    "specific quantified factor 3"
  ]
}
```

`key_factors` must be specific: not "rent is high" but "$28.50/sf vs. market of $24-26/sf = 9-18% premium with 0 TI offset."

---

## Usage Examples

```
/domain-re lease-analysis
Tenant: Momentum Logistics | 45,000 SF industrial | 5-year term | $27.50/sf net
6 months free rent | $18/sf TI | Renewal option 2Ã—5yr at market
[paste lease document or key terms]

/domain-re credit-check
[paste 2-3 years of financial statements or summarize: revenue, EBITDA, debt, key ratios]

/domain-re renewal-economics
Current: 30,000 SF | $24/sf net | expires Dec 2026
Renewal offer: $28/sf net, 3-year term, $8/sf TI
Alternative: $26/sf net competing building | $40k move cost | 2-month downtime

/domain-re rollover-analysis
Tenant: Acme Corp   | SF: 45,000 | Expiry: 2026-12 | Rent: $28/sf | Credit: B+
Tenant: Beta Ltd    | SF: 12,000 | Expiry: 2027-03 | Rent: $31/sf | Credit: A-
Tenant: Gamma Inc   | SF:  8,500 | Expiry: 2027-06 | Rent: $29/sf | Credit: BB
Tenant: Delta Co    | SF: 22,000 | Expiry: 2028-09 | Rent: $25/sf | Credit: A+
```

## Orchestration Steps

Follow in order. Do not skip.

### Step 0: Parse Arguments

Extract:
- `mode` — one of the modes defined in `modes.yml`
- `--quick` flag — if present, use `quick_analysts`
- `input` — lease document, credit report, financial statements, or portfolio data

If mode is missing: ask — "What are you analyzing? (lease-analysis, credit-check, renewal-economics, rollover-analysis)"

### Step 1: Validation Gate (BP1)

1. Read `skills/domain-re/modes.yml`. Confirm mode exists.
2. Get analyst list. Confirm each `skills/domain-re/analysts/{name}.yml` exists.
3. Verify required fields in each YAML.
4. If experimental: warn without blocking.

### Step 2: Concurrency Guard (BP9)

Read `~/.dream-studio/domain-re/checkpoint.json`. If `status: "analyzing"`: offer Resume/Restart/Cancel.

### Step 3: Input Summary (BP8)

Extract and structure key facts from the raw input:
- **Lease analysis**: tenant, space (SF), term, base rent, rent steps, free rent, TI allowance, parking, options, key clauses
- **Credit check**: company, financials provided (years), key ratios visible, industry
- **Renewal economics**: current lease terms, proposed renewal terms, relocation cost estimate, downtime estimate
- **Rollover analysis**: portfolio summary (# leases, total SF, total rent), expiry schedule by year. If the user hasn't provided structured data, ask them to use this format:
  ```
  Tenant: [Name] | SF: [sqft] | Expiry: [YYYY-MM] | Rent: [$/sf net] | Credit: [rating or N/A]
  ```
  Minimum required fields: Tenant, SF, Expiry. Rent and Credit rating improve analysis quality.

Keep to 20 lines max. This structured summary goes to analysts alongside the raw input.

Write initial checkpoint (temp-file-then-rename):
```json
{
  "schema_version": 1,
  "mode": "<mode>",
  "input_hash": "<12-char sha256>",
  "input_summary": "<summary>",
  "timestamp": "<ISO-8601>",
  "status": "analyzing",
  "completed_analysts": {},
  "pending_analysts": ["<analyst1>", ...],
  "mechanical_scores": null,
  "synthesis": null,
  "report_path": null
}
```

Update feed `~/.dream-studio/feeds/domain-re.json`: set `in_progress`.

### Step 4: Dispatch Analyst Subagents

Read `max_parallel` from mode config. Dispatch in waves of `max_parallel`.

For each analyst: substitute `{{name}}`, `{{perspective}}`, `{{input}}` into `prompt_template`. Dispatch via Agent tool in parallel.

**Validate each response (BP3):** signal in enum, confidence 0.0-1.0, reasoning non-empty, key_factors is array. Retry once on failure. If retry fails: mark failed, continue.

Write checkpoint after each wave.

### Step 5: Quorum Check (BP2)

Minimum quorum per mode. If not met: stop with specific error and checkpoint path.

### Step 6: Mechanical Scoring

Map signals to numeric: strong-accept=+2, accept=+1, neutral=0, reject=-1, strong-reject=-2.
Weighted score = signal Ã— confidence Ã— weight.
Aggregate = sum(weighted) / sum(weights).
Flag contested dimensions (analyst pair distance > disagreement_threshold).

### Step 7: Synthesis

For lease-analysis and renewal-economics: always synthesize (contested dimensions likely).
For credit-check: `single-analyst` mode — the skeptic's signal IS the verdict. No synthesis subagent is called regardless of outcome. There is no diplomatic softening on credit risk.
For rollover-analysis: synthesize to produce prioritized action plan.

Synthesis subagent (model: sonnet) receives: all analyst signals, mechanical scores, contested pairs.
Output sections: Recommendation, Contested Dimensions, Key Trade-offs, Action Items.

### Step 8: Write Report

```markdown
# {mode} Analysis: {input_summary}
**Date:** {ISO-8601}
**Analysts:** {list}
**Recommendation:** {aggregate_signal} (confidence: {avg_confidence})

---

{synthesis content}

---

## Raw Analyst Signals

| Analyst | Signal | Confidence | Key Factors |
|---------|--------|------------|-------------|
| ... | ... | ... | ... |

## Disclaimer
This analysis provides institutional-grade frameworks and reasoning. Validate all outputs with qualified RE professionals before making material decisions.
```

Write to: `~/.dream-studio/domain-re/reports/{mode}-{slug}-{YYYY-MM-DD}.md`

### Step 9: Update State

Checkpoint: `status: "complete"`, `report_path`.
Feed `~/.dream-studio/feeds/domain-re.json`: increment `analyses_completed`, set `last_analysis`, clear `in_progress`.

### Step 10: Present Results

1. **Recommendation:** signal + confidence — one line
2. **Contested dimensions** (if any): which analysts disagreed and on what
3. **Key trade-offs:** 2-3 bullets
4. **Action items:** numbered list
5. **Report path**

---

