---
name: analyze
model_tier: opus
description: "Multi-perspective analysis engine — parallel analyst subagents evaluate input from different angles, then synthesis resolves conflicts into a decision memo. Trigger on /analyze or analyze:."
user_invocable: true
args: mode
argument-hint: "[evaluate-offer | evaluate-gig | evaluate-data | evaluate-strategy | evaluate-content | evaluate-repo] [--quick]"
pack: analyze
chain_suggests: []
---

# Analyze — Multi-Perspective Decision Engine

## Before you start
Read `gotchas.yml` in this directory before every invocation.

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
- `evaluate-repo` — Repo bug audit (Forensic, Systemic, Risk, Prevention) — paste pre-pulled PR/issue data
- `--quick` flag — Run only the 2 highest-priority analysts per mode

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

## Detailed Reference

See `examples.md` in this directory for detailed steps, schemas, templates, and integration points.
