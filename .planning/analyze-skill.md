# Spec: Multi-Perspective Analysis Skill (`analyze`)

## Problem Statement

We need a reusable pattern for "multiple specialized analysts evaluate the same input from different angles, then a synthesis agent resolves conflicts and produces a decision." This pattern applies to career offers, client gigs, data analysis, consulting proposals, and any decision that benefits from structured multi-perspective reasoning.

Inspired by ai-hedge-fund's multi-agent architecture, but built natively in dream-studio without external dependencies.

## Chosen Approach: Two-Layer Orchestration

SKILL.md orchestrates: reads YAML configs, spawns analyst subagents in parallel, collects structured signals. Then spawns a synthesis subagent that receives all signals and produces a decision memo.

**Why this over alternatives:**
- Thin orchestrator (all in SKILL.md) causes context bloat from accumulated analyst outputs
- Workflow DAG over-engineers it and depends on unfinished workflow infrastructure
- Two-layer matches dream-studio's proven build pattern (implementer + reviewer as separate subagents)

## Scope

### In
- SKILL.md with orchestration logic (read YAML, dispatch analysts, dispatch synthesis)
- YAML analyst persona definitions (prompt template, weight, output schema)
- YAML mode configurations (which analysts per mode, synthesis strategy)
- 3 launch modes: `evaluate-offer`, `evaluate-gig`, `evaluate-data`
- 12 analyst personas across the 3 modes (4 per mode)
- Structured signal format: `{signal, confidence, reasoning}`
- Hybrid synthesis: mechanical weighted score + LLM narrative
- Disagreement detection and explicit contested-dimension handling
- Checkpoint JSON for resume across sessions
- Feed JSON for dashboard visibility
- Markdown decision memo output
- Career-ops router integration (new `analyze` route)

### Out
- Adaptive weight learning (v2 — needs outcome data first)
- Web UI beyond feed contract
- Backtesting / historical accuracy tracking
- Real-time data fetching (analysts work with provided input, not live APIs)
- Replacing career-evaluate (this complements it)

## Architecture

### File Structure

```
skills/analyze/
├── SKILL.md                # Orchestration logic
├── modes.yml               # Mode → analyst mapping + synthesis config
└── analysts/
    ├── compensation.yml    # evaluate-offer
    ├── growth.yml          # evaluate-offer
    ├── risk.yml            # evaluate-offer
    ├── lifestyle.yml       # evaluate-offer
    ├── profitability.yml   # evaluate-gig
    ├── feasibility.yml     # evaluate-gig
    ├── scope-risk.yml      # evaluate-gig
    ├── timeline.yml        # evaluate-gig
    ├── anomaly.yml         # evaluate-data
    ├── trend.yml           # evaluate-data
    ├── hypothesis.yml      # evaluate-data
    └── validation.yml      # evaluate-data
```

### State Files

```
~/.dream-studio/
├── analyze/
│   └── checkpoint.json     # Resume state
├── feeds/
│   ├── analyze.json        # Dashboard feed
│   └── analyze.schema.json # Feed contract
```

### Signal Scale

5-point scale with numeric mapping for mechanical scoring:

| Signal | Numeric | Meaning |
|--------|---------|---------|
| strong-accept | +2 | Clearly favorable on this dimension |
| accept | +1 | Net positive with minor concerns |
| neutral | 0 | Insufficient signal or balanced trade-off |
| reject | -1 | Net negative, notable concerns |
| strong-reject | -2 | Clearly unfavorable, potential dealbreaker |

### Analyst YAML Schema

```yaml
name: compensation-analyst
perspective: "Total compensation benchmarking and hidden-cost analysis"
weight: 1.0
model: haiku                    # haiku for reads/analysis, sonnet for complex
signal_scale: [strong-accept, accept, neutral, reject, strong-reject]
prompt_template: |
  You are a {name}. Your lens: {perspective}.

  ## Input
  {input}

  ## Instructions
  Analyze this from your specific perspective only. Do not consider
  dimensions outside your expertise.

  Return EXACTLY this JSON:
  {
    "signal": "strong-accept|accept|neutral|reject|strong-reject",
    "confidence": 0.0-1.0,
    "reasoning": "2-3 sentences explaining your assessment",
    "key_factors": ["factor1", "factor2", "factor3"]
  }
```

### modes.yml Schema

```yaml
evaluate-offer:
  description: "Multi-perspective job/contract offer evaluation"
  analysts:
    - compensation
    - growth
    - risk
    - lifestyle
  synthesis:
    strategy: weighted-vote       # weighted-vote | consensus-report
    disagreement_threshold: 2     # signal distance that triggers contested flag
    output: decision-memo         # decision-memo | comparison-table | risk-report

evaluate-gig:
  description: "Freelance/consulting opportunity assessment"
  analysts:
    - profitability
    - feasibility
    - scope-risk
    - timeline
  synthesis:
    strategy: weighted-vote
    disagreement_threshold: 2
    output: decision-memo

evaluate-data:
  description: "Multi-angle dataset or BI analysis"
  analysts:
    - anomaly
    - trend
    - hypothesis
    - validation
  synthesis:
    strategy: consensus-report
    disagreement_threshold: 2
    output: risk-report
```

### Orchestration Flow

```
User: /analyze evaluate-offer <input>
  │
  ├─ 1. SKILL.md reads modes.yml → gets analyst list for mode
  ├─ 2. Reads each analyst YAML → builds subagent prompts
  ├─ 3. Checks checkpoint → skip completed analysts if resuming
  │
  ├─ 4. Spawns analyst subagents IN PARALLEL (Agent tool, model per YAML)
  │     ┌──────────────┬──────────────┬──────────────┐
  │     │ Compensation │   Growth     │    Risk       │  Lifestyle
  │     │   Analyst    │  Analyst     │   Analyst     │  Analyst
  │     └──────┬───────┴──────┬───────┴──────┬────────┘     │
  │            signal         signal         signal        signal
  │
  ├─ 5. Collects all signals → saves checkpoint (status: "analyzing" → "synthesizing")
  │
  ├─ 6. Computes mechanical scores:
  │     - Per-analyst: signal_numeric × confidence × weight
  │     - Aggregate: weighted average across analysts
  │     - Disagreements: flag pairs with distance > threshold
  │
  ├─ 7. Spawns SYNTHESIS subagent (sonnet) with:
  │     - All analyst signals (structured JSON)
  │     - Mechanical scores + aggregate
  │     - Contested dimensions (if any)
  │     - Mode-specific output template
  │
  │     Synthesis agent produces:
  │     - Final recommendation (signal + confidence)
  │     - Narrative reasoning (addresses each contested dimension)
  │     - Key trade-offs summary
  │     - Action items (if applicable)
  │
  ├─ 8. Writes outputs:
  │     - Report: ~/.dream-studio/analyze/reports/<mode>-<topic>-<date>.md
  │     - Checkpoint: status → "complete", report_path set
  │     - Feed: ~/.dream-studio/feeds/analyze.json updated
  │
  └─ 9. Presents decision memo to user
```

### Synthesis Subagent Prompt Structure

```
You are a decision synthesis analyst. You have received structured signals
from {N} specialized analysts who evaluated {input_summary} from different
perspectives.

## Mechanical Scores
Weighted average: {aggregate_score} ({aggregate_signal})
Per analyst: {table of analyst, signal, confidence, weight, weighted_score}

## Contested Dimensions
{For each pair with distance > threshold:}
- {analyst_a} ({signal_a}) vs {analyst_b} ({signal_b}): {dimension}
  You MUST address this disagreement explicitly.

## Your Task
1. Final recommendation: {signal} with confidence
2. For each contested dimension: which analyst's view should dominate and why
3. Key trade-offs: what the user gains and gives up
4. Action items: what to investigate further or negotiate

Output as structured markdown with clear headers.
```

### Checkpoint Schema

```json
{
  "schema_version": 1,
  "mode": "evaluate-offer",
  "input_hash": "sha256-first-12-chars",
  "input_summary": "Senior BI role at Contoso, $140k base",
  "timestamp": "2026-04-18T15:30:00Z",
  "status": "idle|analyzing|synthesizing|complete",
  "completed_analysts": {
    "compensation": {
      "signal": "accept",
      "confidence": 0.85,
      "reasoning": "...",
      "key_factors": ["above-market base", "weak equity"]
    }
  },
  "pending_analysts": ["growth", "risk", "lifestyle"],
  "mechanical_scores": null,
  "synthesis": null,
  "report_path": null
}
```

### Feed Schema

```json
{
  "schema_version": 1,
  "last_updated": "ISO-8601 or null",
  "analyses_completed": 0,
  "last_analysis": {
    "mode": "evaluate-offer",
    "topic": "Senior BI role at Contoso",
    "recommendation": "accept",
    "confidence": 0.78,
    "contested_dimensions": 1,
    "report_path": "...",
    "timestamp": "ISO-8601"
  },
  "in_progress": null
}
```

### Career-Ops Integration

Add to career-ops router dispatch table:

```
analyze → /analyze (with mode from args)
```

Career-evaluate can optionally invoke analyze:
- After qualitative evaluation completes, offer: "Run quantitative multi-perspective analysis?"
- Pass JD + comp details as input to analyze:evaluate-offer
- Append analyze report link to career-evaluate report

### User Extensibility

To add a custom analyst:
1. Create `analysts/my-analyst.yml` following the schema
2. Add `my-analyst` to the relevant mode in `modes.yml`
3. Done — next invocation picks it up automatically

To add a custom mode:
1. Add entry to `modes.yml` with analyst list + synthesis config
2. Invoke with `/analyze my-custom-mode <input>`

## Dependencies

- dream-studio plugin infrastructure (skill loading, Agent tool)
- Agent tool for parallel subagent dispatch
- filesystem-mcp or Write tool for checkpoint/feed/report writes
- No external Python packages, APIs, or runtimes

## Breakpoints & Mitigations

9 failure points identified across the orchestration flow. Each has a concrete mitigation built into the design.

### BP1: YAML Read Failure (Steps 1-2)
**Breaks:** Missing file, malformed YAML, missing required fields.
**Mitigation:** Validate-all-before-spawn gate. Check modes.yml exists, requested mode is defined, each analyst YAML exists with required fields (name, perspective, prompt_template, weight). Fail fast with specific error. Never spawn partial.

### BP2: Analyst Subagent Crash (Step 4)
**Breaks:** 1 of 4 analysts errors out, others succeed.
**Mitigation:** Quorum rule in modes.yml (`min_quorum: 3`). If met: proceed to synthesis noting the gap. If not met: save checkpoint, report failures, stop. Synthesis prompt includes: "Note: {analyst} did not return a signal. Account for this gap."

### BP3: Malformed Analyst Signal (Steps 4-5)
**Breaks:** Analyst returns free-text or invalid signal value.
**Mitigation:** Validate each signal (must have valid `signal`, `confidence` 0-1, non-empty `reasoning`). One retry with explicit format reminder. If retry fails: treat as missing, apply quorum rule. Checkpoint saves raw response for debugging.

### BP4: Unanimous Agreement (Step 6)
**Breaks:** Nothing breaks, but synthesis becomes trivially redundant.
**Mitigation:** Short-circuit. If all analysts agree within 1 signal level and confidence > 0.7: skip synthesis subagent, generate brief mechanical memo inline. Saves 1 subagent. Override with `always_synthesize: true` in modes.yml.

### BP5: Checkpoint Corruption or Staleness (Resume path)
**Breaks:** Corrupted JSON from partial write, or input changed since last run.
**Mitigation:**
- Corruption: temp-file-then-rename. On load, if JSON parse fails, delete and start fresh. Check for orphan `.tmp.json` — if valid, promote it.
- Staleness: compare `input_hash`. If different: ask user "Input changed. Discard partial and restart?"
- Age: warn if checkpoint > 24h old.

### BP6: Synthesis Subagent Failure (Step 7)
**Breaks:** Synthesis crashes, returns incomplete memo, or hallucinates wrong signals.
**Mitigation:**
- Crash: retry once. If second failure, present raw signals + mechanical score as fallback.
- Hallucination: post-check that memo's per-analyst summary matches actual signals. Discrepancy → retry.
- Incomplete: if missing required sections (recommendation, contested dimensions, trade-offs), retry with explicit list.

### BP7: Context Pressure During Orchestration (Steps 4-7)
**Breaks:** Main session hits context threshold mid-analysis.
**Mitigation:** Analyst subagents run in isolated context (don't bloat main session). Orchestrator messages are terse (one-line status, not full reasoning). If context hook fires: checkpoint is already saved, handoff includes checkpoint path, next session resumes via BP5.

### BP8: Input Too Large for Analyst Prompts (Step 3)
**Breaks:** 5-page JD × 4 analysts = heavy token usage, may exceed haiku context.
**Mitigation:** Input summary step before dispatch. Orchestrator creates structured summary (role, company, comp, location, key terms). Analysts get summary, not raw input. Mode-level override: `raw_input: true` for modes that need full text (evaluate-data).

### BP9: Concurrent Write Conflict (Step 8)
**Breaks:** Two `/analyze` calls race on checkpoint.json.
**Mitigation:** Guard at start: if checkpoint shows `status: analyzing`, ask "Analysis already in progress. Resume, restart, or wait?" Atomic temp+rename for all writes.

### modes.yml with Resilience Fields

```yaml
evaluate-offer:
  description: "Multi-perspective job/contract offer evaluation"
  analysts:
    - compensation
    - growth
    - risk
    - lifestyle
  quick_analysts: [compensation, risk]
  max_parallel: 2
  min_quorum: 3
  raw_input: false
  always_synthesize: false
  synthesis:
    strategy: weighted-vote
    disagreement_threshold: 2
    output: decision-memo
```

### Breakpoint Summary

| # | Breakpoint | Mitigation | Cost |
|---|---|---|---|
| BP1 | YAML read failure | Validate-all-before-spawn | Zero — fast fail |
| BP2 | Analyst crash | Quorum (min 3/4) | Graceful degradation |
| BP3 | Malformed signal | Validate + 1 retry → quorum | 1 extra call worst case |
| BP4 | Unanimous agreement | Short-circuit synthesis | Saves 1 subagent |
| BP5 | Stale/corrupt checkpoint | Hash check + age warning | User confirmation |
| BP6 | Synthesis failure | Retry + fallback to raw | Ugly but usable |
| BP7 | Context pressure | Terse orchestrator + checkpoint | Already handled |
| BP8 | Large input | Pre-summarize before dispatch | Saves tokens |
| BP9 | Concurrent writes | Lock check + atomic writes | Zero — guard |
