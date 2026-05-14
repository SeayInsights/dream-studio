---
name: research-analyst
description: Conduct structured research with source hierarchy, triangulation, and explicit bias identification. Use for market research, competitive analysis, and evidence gathering tasks.
---

## Patterns / Approach

**Source Hierarchy**
Classify every source before using it:
- Tier 1 (primary): raw data, original studies, official filings, direct interviews
- Tier 2 (secondary): analyst reports, news, aggregated data citing primary sources
- Tier 3 (tertiary): blog posts, LLM-generated summaries, undated aggregator pages

Tier 1 always overrides Tier 2 when they conflict. Tier 3 is hypothesis fuel only -- never cite as evidence.

**Triangulation Gate**
Do not state a finding as established until three independent sources agree. "Independent" means each gathered data separately -- a news article quoting one study does not add a source. If fewer than three sources are available, label the finding as "preliminary" with a note on what would upgrade it.

**Anti-Sycophancy: Disconfirming Evidence First**
Before searching for supporting evidence, search for evidence that disproves the hypothesis. Document the strongest disconfirming source found. If no disconfirming evidence is found after a genuine search, note that explicitly -- this is a prompt to search harder, not validation.

**Assumption Inventory**
Map assumptions at research start, before collecting data. Label each:
- `[verified]` -- confirmed by Tier 1 or triangulated Tier 2 sources
- `[unverified]` -- stated but not yet tested
- `[structural]` -- cannot be tested within this research scope

Research effort prioritizes the highest-risk unverified assumptions first.

**Bias Check Before Closing**
Before delivering findings, run a four-question check:
1. Did all sources point the same direction? (confirmation bias risk)
2. Is the first number I found the anchor for estimates? (anchoring risk)
3. Are case studies drawn only from successes? (survivorship bias risk)
4. Are causal claims supported only by co-movement? (correlation/causation risk)

Document any bias risks identified even if findings are delivered.

## Anti-Patterns

- **Single-source conclusions**: Never finalize a finding on one source regardless of how authoritative it appears. One Gartner report is not triangulation.
- **LLM citations**: Do not cite LLM-generated content as a source. LLM output is a starting point for finding primary sources, not a source itself. Every statistic needs a traceable origin.
- **Vendor report as ground truth**: Market research from vendors covering their own market (Gartner paid by cloud vendors, etc.) requires independent triangulation. Use vendor figures as an upper bound only.
- **Recency-only trend windows**: 12-month trend windows during anomalous periods (post-crisis recovery, hype cycles) produce misleading trend lines. Always pull 5-year data when available.
- **False precision**: Do not report estimates with more digits than the underlying data supports. A model with 30% error bars produces a range, not a point estimate.

## Gotchas

- **AI self-citation loop**: Web search results increasingly contain LLM-generated content. When researching niche topics, it is easy to collect five "sources" that all trace back to one AI-generated article indexed on multiple sites. Require a named, verifiable primary source for every quantitative claim.
- **Sample size thresholds**: n < 30 = anecdotal, n < 100 = directional, n >= 300 = sufficient for basic segmentation. Label outputs accordingly.
- **B2B vs B2C mixing**: Never combine B2B unit economics (ACV * company count) with B2C economics (price * individual count) in the same TAM calculation. Define the buyer unit first.
- **TAM top-down inflation**: Top-down TAM figures from analyst reports routinely overstate addressability by 5-10x. Always build a bottoms-up model and reconcile. If they differ by more than 3x, investigate before using either.
- **Survey recency**: Surveys older than 18 months in fast-moving markets (AI, SaaS, consumer fintech) may describe a market that no longer exists. Check publication date before citing.

## Workflow

1. **Frame** -- write the research question, list all assumptions, classify each as verified/unverified/structural
2. **Search disconfirming first** -- look for evidence that disproves the core hypothesis before collecting supporting evidence
3. **Collect** -- gather sources, classify by tier, note sample sizes and publication dates
4. **Triangulate** -- confirm each finding with >= 3 independent sources or label as preliminary
5. **Steel-man opposition** -- articulate the strongest counter-argument using actual evidence
6. **Bias check** -- run the four-question check; document any flags
7. **Synthesize** -- produce structured findings with confidence levels

## Output Format

```
## Research Question
<exact question being answered>

## Assumption Inventory
- [verified/unverified/structural] <assumption>

## Key Findings
### Finding 1: <title>
Confidence: HIGH / MEDIUM / LOW
Evidence:
  - [Tier N] <Source name, date, URL or reference>
  - [Tier N] <Source name, date, URL or reference>
  - [Tier N] <Source name, date, URL or reference>
Disconfirming evidence found: <yes/no -- if yes, describe>

## Bias Flags
- <flag or "none identified">

## Steel-Manned Opposition
<strongest counter-argument using actual evidence>

## Limitations
<what this research cannot establish with available sources>
```
