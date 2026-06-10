# Core — Build Lifecycle

## Active work order pre-flight (think / plan / build only)

Before dispatching to `think`, `plan`, or `build`, check for an active work order:

```
py -m interfaces.cli.ds project state
```

If the response contains a `next_work_order` with `status: in_progress` **and**
`pending_tasks > 0`, do NOT enter think/plan/build. Instead print:

> Active WO found: **[title]** with **N** pending tasks.
> Use `ds-workorder execute` and read task descriptions from SQLite instead of ds-core.

Then stop. Only proceed with think/plan/build if **no** in-progress work order with
pending tasks exists.

This check does not apply to `review`, `verify`, `ship`, `handoff`, `recap`, or `explain` —
those modes are safe to run alongside an active work order.

---

## Mode dispatch

0. **Progressive disclosure check:** Before dispatching to a mode, apply the portable skill contract. If a current calibration interface is available in this checkout, use it; otherwise rely on the mode table below. If a mode is locked, show the unlock message and stop.

1. Parse the mode from the argument (first word).
2. If no mode given, infer from the user's message using the keyword table below.
3. If still ambiguous, list available modes and ask.
4. Read `modes/<mode>/SKILL.md` completely.
5. If `modes/<mode>/gotchas.yml` exists, read it before executing.
6. Follow the mode's instructions exactly as written.

| Mode | File | Keywords |
|---|---|---|
| think | modes/think/SKILL.md | think:, spec:, shape ux:, design brief:, research: |
| plan | modes/plan/SKILL.md | plan: |
| build | modes/build/SKILL.md | build:, execute plan: |
| review | modes/review/SKILL.md | review:, review code:, review PR: |
| verify | modes/verify/SKILL.md | verify:, prove it: |
| ship | modes/ship/SKILL.md | ship:, pre-deploy:, deploy: |
| handoff | modes/handoff/SKILL.md | handoff: |
| recap | modes/recap/SKILL.md | recap:, session recap: |
| explain | modes/explain/SKILL.md | explain:, how does, walk me through, what is this doing, why does |

## Shared resources

Core shared modules available to all modes (and other packs):
- `git.md` — branch operations, commit formatting, diff reading
- `format.md` — output formatting, checkpoint format, task progress
- `quality.md` — build commands, test execution, quality gate checklist
- `orchestration.md` — subagent spawning, model selection, review loops
- `traceability.md` — TR-ID validation, traceability file structure
- `repo-map.md` — repository structure mapping

## Tool Recommendations System

Add `--recommend-tools` to think mode to discover external tools (Python packages, MCPs, APIs, SaaS):
```
think: --recommend-tools Build video processing pipeline
```

**How it works:**
1. Keywords extracted from input → TF-IDF search over tool_registry
2. Confidence = (0.7 × TF-IDF similarity) + (0.3 × registry confidence)
3. Top 5 tools with confidence >0.7 appended to spec.md

**Customizing tool_registry:** Use the current Dream Studio tool registry interface when available. If no maintained registry CLI exists in this checkout, treat registry edits as future implementation work instead of calling retired helper paths.

**Detailed documentation:** See `references/tool-recommendations.md` for TF-IDF algorithm, schema, API integration, troubleshooting.

## Research Flag System

Add `--research` to think mode for web-based research and source triangulation:
```
think: --research Should we use NetworkX or igraph for graph analysis?
```

**How it works:**
1. Topics extracted → WebSearch with 30-day cache → source triangulation
2. Tier filtering: Tier 1 (official docs, GitHub, RFCs) + Tier 2 (Real Python, O'Reilly)
3. Confidence = source quality + recency + consensus across sources
4. Research findings appended to spec.md

**Source tiers:**
- **Tier 1 (Official):** GitHub, official docs, academic papers, RFCs
- **Tier 2 (Reputable):** Real Python, O'Reilly, verified technical blogs
- **Tier 3 (Community):** Stack Overflow, Reddit (excluded from output)

**When to use:** New/emerging tech, library comparisons, best practices validation. Adds 2-5 min to think mode.

**Cache management:** Research artifacts are advisory/local-only by default. Use `py interfaces/cli/research_cache.py <command>` for the file-backed cache, or `control.research.web.invalidate_cache("topic")` for the SQLite `research_cache` advisory table.

**Detailed documentation:** See `references/research-system.md` for source tier definitions, confidence scoring, triangulation algorithm, troubleshooting.
