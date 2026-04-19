---
name: analyze
description: "Multi-perspective analysis engine — parallel analyst subagents evaluate input from different angles, then synthesis resolves conflicts into a decision memo. Trigger on /analyze or analyze:."
user_invocable: true
args: mode
argument-hint: "[evaluate-offer | evaluate-gig | evaluate-data | evaluate-strategy | evaluate-content] [--quick]"
---

# Analyze — Multi-Perspective Decision Engine

## Trigger
`/analyze <mode> <input>`, `analyze:`, or invoked by other skills (e.g., career-evaluate)

## Purpose
Spawn specialized analyst subagents in parallel, each evaluating the same input from a different perspective. Collect structured signals, compute mechanical scores, detect disagreements, and synthesize into a decision memo.

Inspired by multi-agent hedge fund architectures, adapted for career offers, client gigs, data analysis, and any decision benefiting from structured multi-perspective reasoning.

## Modes
- `evaluate-offer` — Job/contract offer evaluation (Compensation, Growth, Risk, Lifestyle)
- `evaluate-gig` — Freelance/consulting assessment (Profitability, Feasibility, Scope-Risk, Timeline)
- `evaluate-data` — Dataset/BI analysis (Anomaly, Trend, Hypothesis, Validation)
- `evaluate-strategy` — C-level business strategy evaluation (CFO, CTO, CMO, CPO, CEO)
- `evaluate-content` — Content quality + SEO readiness (SEO, CMO)
- `--quick` flag — Run only the 2 highest-priority analysts per mode

## Signal Scale

All analysts return signals on this 5-point scale:

| Signal | Numeric | Meaning |
|--------|---------|---------|
| strong-accept | +2 | Clearly favorable on this dimension |
| accept | +1 | Net positive with minor concerns |
| neutral | 0 | Insufficient signal or balanced trade-off |
| reject | -1 | Net negative, notable concerns |
| strong-reject | -2 | Clearly unfavorable, potential dealbreaker |

## Analyst Output Schema

Every analyst must return exactly this JSON structure:
```json
{
  "signal": "strong-accept|accept|neutral|reject|strong-reject",
  "confidence": 0.0-1.0,
  "reasoning": "2-3 sentences explaining the assessment",
  "key_factors": ["factor1", "factor2", "factor3"]
}
```

---

## Orchestration Steps

Follow these steps in order. Do not skip steps. Do not proceed past a failed gate.

### Step 0: Parse Arguments

Extract from user input:
- `mode` — one of the modes defined in `modes.yml` (e.g., `evaluate-offer`)
- `--quick` flag — if present, use `quick_analysts` list instead of `analysts`
- `input` — everything after the mode and flags is the analysis input

If mode is missing or not found in `modes.yml`, stop: "Unknown mode `{mode}`. Available modes: evaluate-offer, evaluate-gig, evaluate-data."

### Step 1: Validation Gate (BP1)

Before spawning any subagents, validate the full configuration:

1. Read `skills/analyze/modes.yml`. Confirm the requested mode exists.
2. Get the analyst list for this mode (or `quick_analysts` if `--quick`).
3. For each analyst in the list, confirm `skills/analyze/analysts/{name}.yml` exists.
4. Read each analyst YAML. Verify required fields: `name`, `perspective`, `weight`, `model`, `prompt_template`.
5. If ANY file is missing or ANY required field is absent: **stop immediately** with a specific error.
   Example: "Validation failed: analysts/growth.yml missing field `prompt_template`."
6. Check mode's `status` field. If `experimental`: warn user — "Mode `{mode}` is experimental. Results may vary."
7. Check each analyst's `tested` field. If any analyst has `tested: false`: warn — "Untested analysts in this mode: {list}. Proceed?" Wait for confirmation before continuing.

Do NOT proceed to Step 2 if validation fails.

### Step 2: Concurrency Guard (BP9)

Read `~/.dream-studio/analyze/checkpoint.json`.

- If `status` is `"analyzing"`: ask user — "Analysis already in progress ({checkpoint.input_summary}). Resume, restart, or cancel?"
  - **Resume** → go to Step 4 (resume path)
  - **Restart** → reset checkpoint to `{"schema_version": 1, "status": "idle"}`, continue
  - **Cancel** → stop
- If `status` is `"synthesizing"`: ask user — "Previous analysis completed analysts but synthesis was interrupted. Resume synthesis or restart?"
  - **Resume** → go to Step 7 (synthesis)
  - **Restart** → reset checkpoint, continue
- If `status` is `"idle"` or `"complete"`: continue normally

### Step 3: Input Summary (BP8)

Read the mode's `raw_input` setting from `modes.yml`.

- If `raw_input: false` (default for offers/gigs): create a structured summary of the user's input. Extract key facts only:
  - For evaluate-offer: company, role, level, location, base, bonus, equity, benefits, notable terms
  - For evaluate-gig: client, project description, rate, timeline, deliverables, payment terms
  - Keep to 10-15 lines max. This summary is what analysts receive (not the raw input).
  - Store both `input_hash` (SHA-256 first 12 chars of raw input) and the summary.

- If `raw_input: true` (evaluate-data): pass the full input to analysts. Still compute `input_hash`.

Write initial checkpoint:
```json
{
  "schema_version": 1,
  "mode": "<mode>",
  "input_hash": "<12-char hash>",
  "input_summary": "<summary or first 100 chars>",
  "timestamp": "<ISO-8601>",
  "status": "analyzing",
  "completed_analysts": {},
  "pending_analysts": ["<analyst1>", "<analyst2>", ...],
  "mechanical_scores": null,
  "synthesis": null,
  "report_path": null
}
```

Write using temp-file-then-rename:
1. Write to `~/.dream-studio/analyze/checkpoint.tmp.json`
2. Rename to `checkpoint.json`

Update feed (`~/.dream-studio/feeds/analyze.json`): set `in_progress` with mode, topic, analysts_completed=0, analysts_total, started_at.

### Step 4: Dispatch Analyst Subagents

Read `max_parallel` from mode config (default: 2).

Get the list of pending analysts (all analysts if fresh start, or `pending_analysts` from checkpoint if resuming).

**For each wave of `max_parallel` analysts:**

1. Read each analyst's YAML file.
2. Build the subagent prompt by substituting placeholders in `prompt_template`:
   - `{{name}}` → analyst's `name` field
   - `{{perspective}}` → analyst's `perspective` field
   - `{{input}}` → the input summary (from Step 3) or raw input
3. Dispatch analysts in this wave using the Agent tool **in parallel**:
   - `model` → from analyst YAML (`haiku` for most)
   - `description` → "{analyst name} analysis"
   - `prompt` → the built prompt from step 2
4. Wait for all agents in this wave to complete.
5. **Validate each response (BP3):**
   - Parse the response as JSON.
   - Check `signal` is one of: `strong-accept`, `accept`, `neutral`, `reject`, `strong-reject`.
   - Check `confidence` is a number between 0.0 and 1.0.
   - Check `reasoning` is a non-empty string.
   - Check `key_factors` is an array of strings.
   - **If validation fails:** retry that analyst once with this added instruction: "Your previous response was not valid JSON with the required fields. Return ONLY the JSON object with: signal, confidence, reasoning, key_factors."
   - **If retry also fails:** mark analyst as failed. Do NOT block the pipeline — continue with remaining analysts.
6. Save each valid signal to checkpoint under `completed_analysts`. Remove from `pending_analysts`. Update feed `in_progress.analysts_completed`.
7. Write checkpoint (temp-file-then-rename) after each wave completes.
8. Repeat for next wave until all analysts dispatched.

### Step 5: Quorum Check (BP2)

After all waves complete, count successful analysts.

- Read `min_quorum` from mode config.
- If `--quick` mode: adjust quorum to `min(min_quorum, len(quick_analysts))`.
- If successful analysts >= `min_quorum`: proceed to Step 6.
- If successful analysts < `min_quorum`: **stop**. Save checkpoint. Report:
  "Quorum not met: {successful}/{total} analysts returned valid signals (need {min_quorum}). Failed: {list}. Checkpoint saved — fix issues and resume."

### Step 6: Mechanical Scoring

Map each analyst's signal to numeric value:
- `strong-accept` = +2, `accept` = +1, `neutral` = 0, `reject` = -1, `strong-reject` = -2

For each analyst, compute weighted score:
```
weighted_score = numeric_signal × confidence × weight
```

Compute aggregate:
```
aggregate = sum(weighted_scores) / sum(weights of successful analysts)
```

Map aggregate back to signal:
- aggregate >= 1.5 → `strong-accept`
- aggregate >= 0.5 → `accept`
- aggregate > -0.5 → `neutral`
- aggregate > -1.5 → `reject`
- aggregate <= -1.5 → `strong-reject`

**Detect disagreements:** For every pair of analysts, compute signal distance (absolute difference of numeric values). If distance > `disagreement_threshold` from mode config: flag as contested dimension.

Example: compensation-analyst says `accept` (+1) and risk-analyst says `strong-reject` (-2) → distance = 3 > threshold 2 → contested.

Save mechanical scores to checkpoint:
```json
{
  "mechanical_scores": {
    "per_analyst": {
      "compensation": {"numeric": 1, "confidence": 0.85, "weight": 1.0, "weighted": 0.85},
      "risk": {"numeric": -2, "confidence": 0.9, "weight": 1.0, "weighted": -1.8}
    },
    "aggregate": -0.24,
    "aggregate_signal": "neutral",
    "contested_dimensions": [
      {"analyst_a": "compensation", "signal_a": "accept", "analyst_b": "risk", "signal_b": "strong-reject", "distance": 3}
    ]
  }
}
```

### Step 6b: Deduplication Check (BP10)

Before synthesis, check for cross-analyst signal contamination:

1. Collect all `key_factors` from all analysts.
2. For each pair of analysts, fuzzy-match their key_factors (same concept, different wording counts as a match).
3. If the same factor appears in 2+ analysts' key_factors, flag as a **shared factor**.
4. Pass shared factors to the synthesis prompt: "These factors were cited by multiple analysts: {list}. Weight each shared factor once in your assessment, not per-analyst. The independent signals are what matter."

This prevents domain-bleed in modes like evaluate-strategy where C-level analysts may inadvertently evaluate the same dimension.

### Step 7: Synthesis Decision (BP4 Short-Circuit)

**Check for unanimous agreement:** If ALL analysts agree within 1 signal level (max distance between any pair <= 1) AND average confidence > 0.7 AND mode has `always_synthesize: false`:

→ **Short-circuit.** Skip the synthesis subagent. Generate a brief mechanical memo:

```markdown
# Analysis: {mode} — {input_summary}

## Recommendation: {aggregate_signal} (confidence: {avg_confidence})

All {N} analysts converged. No contested dimensions.

| Analyst | Signal | Confidence | Key Factors |
|---------|--------|------------|-------------|
| ... | ... | ... | ... |

**Combined key factors:** {union of all key_factors, deduplicated}
```

→ Skip to Step 9 (output).

**Otherwise, dispatch synthesis subagent:**

Spawn one Agent with `model: sonnet` and this prompt:

```
You are a decision synthesis analyst. You received structured signals from
{N} specialized analysts who evaluated: "{input_summary}"

## Analyst Signals
{For each analyst: name, signal, confidence, reasoning, key_factors — as structured data}

## Mechanical Scores
- Per analyst: {table: analyst, numeric, confidence, weight, weighted_score}
- Aggregate weighted score: {aggregate} → {aggregate_signal}

## Contested Dimensions
{For each contested pair:}
- {analyst_a} ({signal_a}) vs {analyst_b} ({signal_b}): distance {distance}
  YOU MUST address this disagreement explicitly — which view should dominate and why.

{If no contested dimensions:}
No major disagreements, but explain nuances between analyst perspectives.

## Your Task
Produce a decision memo with EXACTLY these sections:

### Recommendation
Final signal (one of: strong-accept, accept, neutral, reject, strong-reject) with confidence (0-1).
One sentence summary.

### Contested Dimensions
For each flagged disagreement: which analyst's view should dominate and why.
If none flagged, note the convergence and any subtle tensions.

### Key Trade-offs
What the user gains and gives up. Be specific, not generic.

### Action Items
Concrete next steps: what to investigate, negotiate, or verify before deciding.

Output as clean markdown. No JSON wrapping. No preamble.
```

**Post-check (BP6):** After synthesis returns:
1. Verify the memo contains all 4 required sections (Recommendation, Contested Dimensions, Key Trade-offs, Action Items). If missing any: retry once with "Your response was missing these sections: {list}. Include all 4."
2. If the memo references an analyst signal that doesn't match the actual signal (e.g., claims risk-analyst said "accept" when they said "reject"): retry once with "Factual error: {analyst} actually returned {actual_signal}, not {claimed_signal}. Correct this."
3. If second retry fails: use the memo as-is but prepend a warning: "Note: Synthesis had factual inconsistencies. Raw analyst signals are included below for verification." Then append the raw signals table.

Save synthesis result to checkpoint.

### Step 8: Write Report

Build the final report markdown:

```markdown
# {mode} Analysis: {input_summary}
**Date:** {ISO-8601 date}
**Mode:** {mode}
**Analysts:** {N} ({list of analyst names})
**Aggregate Score:** {aggregate} → {aggregate_signal}

---

{synthesis memo content — either the full synthesis or the short-circuit memo}

---

## Raw Analyst Signals

| Analyst | Signal | Confidence | Weight | Weighted Score | % of Total | Key Factors |
|---------|--------|------------|--------|----------------|------------|-------------|
| {name} | {signal} | {confidence} | {weight} | {weighted} | {pct_of_total} | {key_factors joined} |
| ... | ... | ... | ... | ... | ... | ... |

**Weight note:** {If any analyst's weight exceeds 15% of total weight pool, note: "{analyst} carries {pct}% weight — above the 15% equal-share threshold. This is intentional for the {mode} mode."}

## Methodology
- Signal scale: strong-accept (+2) to strong-reject (-2)
- Weighted score = signal_numeric x confidence x weight
- Aggregate = sum(weighted_scores) / sum(weights)
- Disagreement threshold: {threshold} signal levels
```

Write the report to: `~/.dream-studio/analyze/reports/{mode}-{topic_slug}-{YYYY-MM-DD}.md`
- `topic_slug`: lowercase, spaces→hyphens, max 40 chars, alphanumeric+hyphens only

### Step 9: Update State

**Update checkpoint** (temp-file-then-rename):
```json
{
  "status": "complete",
  "report_path": "<path to report>",
  "synthesis": {
    "recommendation": "<signal>",
    "confidence": 0.0-1.0
  }
}
```

**Update feed** (`~/.dream-studio/feeds/analyze.json`):
- Increment `analyses_completed`
- Set `last_analysis`: mode, topic, recommendation, confidence, contested_dimensions count, report_path, timestamp
- Set `in_progress`: null
- Set `last_updated`: current ISO-8601 timestamp

Write feed using temp-file-then-rename. Validate `schema_version` is 1 before writing. If validation fails, preserve existing feed file and warn.

### Step 10: Present Results

Show the user:

1. **Headline:** "{aggregate_signal} (confidence: {avg_confidence})" — one line
2. **Contested dimensions** (if any): one line per contested pair
3. **Key trade-offs** from synthesis: 2-3 bullet points
4. **Action items** from synthesis: numbered list
5. **Report path:** "Full report saved to: {report_path}"

Keep presentation concise. The report has the full detail — the in-conversation output is a summary.

6. **Verdict prompt:** Ask the user: "**Accept**, **discard**, or **re-run**?"
   - **Accept** → done, analysis stands
   - **Discard** → delete the report file, reset checkpoint to `{"schema_version": 1, "status": "idle"}`, decrement `analyses_completed` in feed, clear `last_analysis`, set `in_progress: null`. Confirm: "Analysis discarded."
   - **Re-run** → reset checkpoint to idle, restart from Step 0 with same input

---

## Resume Logic (BP5)

When resuming from a checkpoint (user chose "Resume" in Step 2):

1. Read `~/.dream-studio/analyze/checkpoint.json`.
2. Verify `input_hash`: ask the user to provide the input again. Compute its hash.
   - If hash matches: resume from where we left off.
   - If hash differs: warn "Input has changed since the last run. Discard partial results and restart?" Wait for confirmation.
3. Check `status`:
   - `"analyzing"`: go to Step 4 with `pending_analysts` from checkpoint. `completed_analysts` are already saved — skip them.
   - `"synthesizing"`: all analysts are done. Go to Step 6 (mechanical scoring) — recompute from saved signals, then Step 7 (synthesis).
   - `"complete"`: report already exists. Show: "Previous analysis complete. Report at {report_path}. Run a new analysis?"
4. If checkpoint is older than 24 hours, warn: "This analysis was started {time_ago}. Context may have changed. Resume or restart?"

**Orphan tmp file recovery:** Before reading `checkpoint.json`, check if `checkpoint.tmp.json` exists. If it does AND it contains valid JSON: rename it to `checkpoint.json` (it means we crashed after write but before rename). If it's invalid JSON: delete it.

---

## Quick Mode

When `--quick` flag is present:

1. Read `quick_analysts` from mode config instead of `analysts`.
2. Adjust quorum: `min_quorum = min(mode.min_quorum, len(quick_analysts))`.
3. Everything else stays the same — validation, dispatch, scoring, synthesis all work identically, just with fewer analysts.
4. Report and checkpoint reflect the reduced analyst set.

Quick mode is for low-stakes decisions where speed matters more than thoroughness. Use full mode for decisions with significant financial or career impact.

---

## User Extensibility

### Adding a custom analyst

1. Create a new YAML file at `skills/analyze/analysts/{name}.yml`
2. Follow this schema:
   ```yaml
   name: my-custom-analyst
   perspective: "One-line description of evaluation lens"
   weight: 1.0
   model: haiku
   signal_scale:
     - strong-accept
     - accept
     - neutral
     - reject
     - strong-reject
   prompt_template: |
     You are a {{name}}. Your lens: {{perspective}}.

     ## Input
     {{input}}

     ## Your Task
     [Specific evaluation criteria for this analyst]

     Return EXACTLY this JSON. No markdown. No extra text.
     {"signal": "...", "confidence": 0.0-1.0, "reasoning": "2-3 sentences", "key_factors": ["f1", "f2", "f3"]}
   ```
3. Add the analyst name to a mode in `modes.yml` under `analysts` and/or `quick_analysts`.

### Adding a custom mode

Add an entry to `modes.yml`:
```yaml
my-custom-mode:
  description: "What this mode evaluates"
  analysts:
    - analyst-a
    - analyst-b
    - analyst-c
  quick_analysts:
    - analyst-a
    - analyst-b
  max_parallel: 2
  min_quorum: 2
  raw_input: false
  always_synthesize: false
  synthesis:
    strategy: weighted-vote
    disagreement_threshold: 2
    output: decision-memo
```

Invoke with `/analyze my-custom-mode <input>`. No skill code changes needed.

---

## Integration Points

### Career-Ops Integration
Career-ops router can dispatch to this skill:
- Route: `analyze` → invoke `/analyze` with mode from args
- Career-evaluate can optionally call `/analyze evaluate-offer` after qualitative evaluation and append the report link

### Other Skills
Any skill can invoke analyze by reading this SKILL.md and following the orchestration steps. The analyze skill is self-contained — it only reads its own YAML configs and writes to its own state directory.

---

## Next in Pipeline
- Standalone: presents decision memo directly to user
- After career-evaluate: appends quantitative analysis to qualitative report
- Before a decision: user reviews memo, then acts

---

## Anti-patterns

- **Skipping the validation gate** — Never dispatch analysts without verifying all YAMLs exist and parse correctly. A missing analyst mid-run wastes subagent calls and produces confusing partial results.
- **Ignoring quorum** — If quorum isn't met, the analysis is unreliable. Don't synthesize from 1 of 4 analysts.
- **Proceeding with broken synthesis** — If synthesis hallucinates signals, the memo is misleading. Always post-check and retry.
- **Dispatching all analysts at once** — Respect `max_parallel`. Overwhelming the Agent tool with too many concurrent calls can cause failures.
- **Skipping checkpoint writes** — Every analyst completion must be checkpointed. If the session dies, uncheckpointed work is lost.
- **Hardcoding analyst logic in SKILL.md** — All analyst behavior lives in YAML files. The skill orchestrates, it doesn't analyze.
- **Cross-domain analysis** — Each analyst must stay in its lane. If a compensation-analyst comments on career growth, the signal is polluted. Prompt templates enforce this boundary.
- **Skipping the input summary step** — Large inputs sent directly to haiku analysts risk context overflow and degrade signal quality. Always summarize unless `raw_input: true`.
