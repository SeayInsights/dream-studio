# Spec: Workflow Coverage, Token Efficiency & Feature Activation

**Date:** 2026-04-30
**Status:** Awaiting Director approval

---

## Problem Statement

dream-studio has 35+ skill modes, 14 workflows, a SQLite telemetry DB, token tracking pipeline, and workflow cost estimation — but these systems don't talk to each other. Skills complete without suggesting next steps. Token costs are tracked after the fact but never used to make pre-run decisions. Some features (skill_metrics.py lib, Sentry telemetry) are dead code. Many skills have no workflow home. The result: manual orchestration where automation should exist, and token waste where compression should exist.

---

## Current State Assessment

### A. Feature Activation Status

| Feature | Status | Evidence |
|---|---|---|
| **studio_db.py** (SQLite) | ACTIVE | 6 tables, on-pulse imports telemetry buffer every prompt |
| **workflow_cost.py** | ACTIVE but passive | Called when listing workflows — shows estimates but never gates execution |
| **on-token-log.py** | ACTIVE | Logs session tokens to token-log.md on Stop |
| **on-skill-metrics.py** | ACTIVE | Logs every skill invocation to skill-usage.jsonl |
| **on-quality-score.py** | ACTIVE | Infers success/failure heuristically, writes telemetry-buffer.jsonl |
| **on-pulse.py** | ACTIVE | Batches telemetry into SQLite, health dashboard, auto-archive |
| **hooks/lib/skill_metrics.py** | DEAD | Never imported — duplicate of on-skill-metrics.py hook |
| **hooks/lib/telemetry.py** (Sentry) | DEAD | Requires SENTRY_DSN env var; no production code calls it |
| **benchmark_tokens.py** | EXISTS | Script for analyzing token-log.md overhead — manual invocation only |

### B. Token Intelligence Pipeline (Current)

```
on-skill-metrics (PostToolUse) → skill-usage.jsonl (invocation log)
          ↓
on-quality-score (Stop) → telemetry-buffer.jsonl (success/fail per skill)
          ↓
on-pulse (UserPromptSubmit) → SQLite (batch import, summaries, 90-day prune)
          ↓
workflow_cost.py → pre-run estimates (when listing workflows only)
          ↓
on-token-log (Stop) → token-log.md (session-level audit)
```

**Gap:** Token data flows AFTER execution. Nothing uses this data BEFORE execution to:
- Warn "this workflow will cost ~15K tokens, proceed?"
- Select model tier based on historical cost data
- Skip optional nodes when context budget is tight

### C. Skill-to-Workflow Coverage

#### Skills WITH workflow coverage (15/35)
| Skill | Workflows |
|---|---|
| think | idea-to-pr, prototype, feature-research, comprehensive-review |
| plan | idea-to-pr, fix-issue, safe-refactor, feature-research |
| build | idea-to-pr, fix-issue, hotfix, safe-refactor, optimize |
| review | idea-to-pr, comprehensive-review, project-audit |
| verify | idea-to-pr, fix-issue, optimize |
| ship | idea-to-pr |
| debug | fix-issue, hotfix |
| harden | project-audit, studio-onboard |
| secure | idea-to-pr, security-audit, comprehensive-review |
| structure-audit | self-audit, studio-onboard |
| scan | security-audit |
| dast | security-audit |
| binary-scan | security-audit |
| mitigate | security-audit |
| game-dev | game-feature |

#### Skills WITHOUT workflow coverage (20/35)
| Skill | Pack | Natural workflow home |
|---|---|---|
| **polish** | quality | After build page/component, before verify. UI quality gate. |
| **coach** | quality | After recap or on-demand. Meta-evaluation of session. |
| **learn** | quality | After debug (>=3 iterations), after recap. Pattern capture. |
| **explain** | core | Before think (orientation). Before debug (understanding). |
| **handoff** | core | Auto at context threshold. Session continuity. |
| **recap** | core | After ship or session end. Build memory. |
| **comply** | security | After scan findings. Compliance mapping. |
| **netcompat** | security | After deploy. Network compatibility check. |
| **dashboard** (security) | security | After scan cycle. Metrics export. |
| **design** | domains | Before build page. Creative brief → implementation. |
| **mcp-build** | domains | Feature workflow for MCP servers. |
| **dashboard-dev** | domains | Feature workflow for Tauri dashboards. |
| **client-work** | domains | End-to-end client delivery pipeline. |
| **career ops** | career | Standalone — job search lifecycle. |
| **career scan** | career | Standalone — job discovery. |
| **career evaluate** | career | Standalone — offer analysis. |
| **career apply** | career | Standalone — application materials. |
| **career track** | career | Standalone — pipeline management. |
| **career pdf** | career | Standalone — resume generation. |
| **setup** | setup | First-run only — already in studio-onboard. |

---

## Approaches

### Approach A: Workflow-First (Every skill gets a workflow home)

Create/update workflows so every skill has at least one workflow context. Add a "skill-suggest" hook that fires after skill completion to recommend the natural next step.

**Pros:** Full coverage, predictable behavior, easy to discover via `workflow list`
**Cons:** 8-10 new workflows to build and maintain, some skills are inherently ad-hoc (explain, coach)
**Complexity:** High (2-3 sessions)

### Approach B: Chain-Suggest + Selective Workflows (Recommended)

Instead of forcing every skill into a workflow, add two mechanisms:
1. **Chain-suggest metadata** in each SKILL.md — `next_suggests:` field that names what should come next
2. **on-skill-complete hook** that reads this metadata and prints a suggestion
3. **New workflows only where the chain is 3+ steps and repeatable**

Skills that are inherently ad-hoc (explain, coach, handoff, recap) get chain-suggest but no dedicated workflow.

**Pros:** Right-sized — workflows where they add value, suggestions where they don't. Lower maintenance.
**Cons:** Chain-suggest is advisory only — user can ignore it
**Complexity:** Medium (1-2 sessions)

### Approach C: Python Context Compiler + Workflow Templates

Build a Python context compilation layer that workflows use to minimize token consumption. Combine with parameterized workflow templates (e.g., `audit-to-fix.yaml` works for any audit type).

**Pros:** Addresses token efficiency AND workflow coverage. Workflows become cheaper to run.
**Cons:** Largest engineering effort. Python scripts become critical path.
**Complexity:** High (2-3 sessions)

---

## Recommendation: Approach B + C fully integrated

Combine chain-suggest + selective workflows (B) with the FULL Python context efficiency layer (C). The context compiler isn't optional — it's where the compounding token savings live. Every workflow node that spawns a subagent pays the context tax. With 8-node workflows running regularly, a 50-60% reduction per node means the system pays for itself on the first run.

The Python layer has 5 scripts, each solving a different waste pattern:

| Script | Waste it eliminates | Savings |
|---|---|---|
| `repo_context.py` | Every agent does its own file tree exploration | ~50% on exploration |
| `context_compiler.py` | Agents load full SKILL.md + orchestration.md (~2000 words) | ~60% per agent |
| `prompt_assembler.py` | No shared static prefix → no prompt cache hits across agents | ~40% on SKILL.md |
| `findings_summarizer.py` | Raw prose findings passed between nodes (~1500 words) | ~70% on inter-node |
| `session_cache.py` | Multiple nodes re-read same session files from disk | ~30% on file I/O |

**Combined impact on an 8-node workflow:** If each node currently costs ~8K tokens on context overhead, and we cut that by 50% average, that's ~32K tokens saved per workflow run. Over a week of active use (10+ workflow runs), that's 300K+ tokens — more than an entire context window.

---

## Design: Skill Workflow Map

### Where each skill fits in the lifecycle

```
                    ┌─────────────────────────────────────┐
                    │          ORIENTATION PHASE           │
                    │  explain → think → plan              │
                    └──────────────┬──────────────────────┘
                                   │
                    ┌──────────────▼──────────────────────┐
                    │         IMPLEMENTATION PHASE         │
                    │  design? → build → polish? → review  │
                    └──────────────┬──────────────────────┘
                                   │
                    ┌──────────────▼──────────────────────┐
                    │          VALIDATION PHASE            │
                    │  secure → verify → comply?           │
                    └──────────────┬──────────────────────┘
                                   │
                    ┌──────────────▼──────────────────────┐
                    │           DELIVERY PHASE             │
                    │  ship → recap → learn → handoff      │
                    └─────────────────────────────────────┘
                                   │
                    ┌──────────────▼──────────────────────┐
                    │         MAINTENANCE PHASE            │
                    │  debug → harden → structure-audit    │
                    │  scan → dast → mitigate → dashboard  │
                    │  optimize (full pipeline)            │
                    └─────────────────────────────────────┘
                                   │
                    ┌──────────────▼──────────────────────┐
                    │          META / ADVISORY             │
                    │  coach → self-audit → setup          │
                    └─────────────────────────────────────┘
```

### Where POLISH fits specifically

Polish belongs between `build` and `review` for UI work:

```
build page/component → polish (score 7 dimensions) → fix issues → re-score → review
```

**Trigger condition:** Auto-invoke polish after `build` when the build involved:
- `build page:`, `build component:`, `build ui:`, `redesign:`
- Any task that modified `.tsx`, `.vue`, `.svelte`, `.astro`, or `.css` files

**NOT triggered for:** API routes, backend logic, CLI tools, scripts, configs

### Chain-Suggest Metadata (new field in each SKILL.md)

```yaml
# Added to frontmatter of each SKILL.md
chain_suggests:
  - condition: "always"                    # or "ui_build", "findings_found", "critical_findings"
    next: "plan"
    prompt: "Spec approved → ready to plan?"
```

### Complete chain-suggest map:

| Skill | Condition | Suggests Next | Prompt |
|---|---|---|---|
| think | always | plan | "Spec approved — plan the tasks?" |
| plan | always | build | "Plan ready — start building?" |
| build | ui files changed | polish | "UI changes detected — run polish?" |
| build | always | review | "Build complete — review the code?" |
| polish | always | review | "Polish complete — run code review?" |
| review | findings found | build (fix) | "Findings to fix — re-enter build?" |
| review | clean | verify | "Review clean — verify it works?" |
| secure | critical findings | mitigate | "Critical findings — run mitigate?" |
| secure | clean | verify | "Security clean — verify?" |
| verify | always | ship | "Verified — ready to ship?" |
| ship | always | recap | "Shipped — capture recap?" |
| debug | root cause found | plan (fix) | "Root cause identified — plan the fix?" |
| debug | >=3 iterations | learn | "Complex debug — capture lesson?" |
| harden | gaps found | build (fill) | "Gaps found — fill them?" |
| structure-audit | violations found | plan (refactor) | "Violations found — plan refactor?" |
| scan | vulnerabilities found | mitigate | "Vulnerabilities found — run mitigate?" |
| mitigate | fixes generated | build | "Mitigations ready — apply fixes?" |
| recap | root cause found | learn | "Root cause in recap — capture lesson?" |
| learn | pattern promoted | (none) | "Lesson captured." |
| explain | (none) | (none) | Informational — no chain. |
| coach | (none) | (none) | Advisory — no chain. |
| handoff | (none) | (none) | Terminal — session ending. |

---

## Design: New Workflows to Create

### Priority 1 — High value, repeatable patterns

#### 1. `audit-to-fix.yaml` (Generic audit → plan → build chain)
```
audit (parameterized: harden|secure|structure-audit|scan)
  → synthesize findings
  → plan fixes
  → [Director gate]
  → build fixes
  → verify
  → report
```
**Replaces:** Manual "ok now plan that" after every audit.

#### 2. `ui-feature.yaml` (UI-aware build pipeline)
```
think → plan → build → polish → review → verify → ship
```
**Difference from idea-to-pr:** Inserts polish after build, only for UI work.

#### 3. `client-deliverable.yaml` (PLMarketing delivery pipeline)
```
intake (requirements) → plan → build powerbi/flow/app
  → validate (data checks)
  → screenshot key visuals
  → generate summary doc
  → [Director gate]
  → deliver
```
**Why:** Your day job involves repeated client deliveries — formalize the pattern.

### Priority 2 — Useful but less frequent

#### 4. `career-pipeline.yaml` (Job search lifecycle)
```
scan → evaluate (parallel: each match) → [gate: which to pursue]
  → apply (tailored materials) → track → pdf
```

#### 5. `security-remediation.yaml` (Full security cycle)
```
scan → dast → synthesize → mitigate → comply → verify → dashboard
```
**Difference from security-audit:** Includes mitigate + comply + dashboard export.

#### 6. `weekly-maintenance.yaml` (Cron-scheduled hygiene)
```
self-audit → dep-check → stale-branch-cleanup → pulse → report
```

### Priority 3 — Nice to have

#### 7. `mcp-feature.yaml` (MCP server development)
```
think → plan → mcp-build → review → verify → ship
```

#### 8. `design-to-build.yaml` (Creative brief → implementation)
```
design (brief + variations) → [Director picks direction]
  → build → polish → review → ship
```

---

## Design: Token Intelligence System

### Pre-Run Cost Gate (new)

Before any workflow runs, show estimated cost and ask for confirmation:

```
┌─ Workflow Cost Estimate ─────────────────────┐
│  think              12,000 tokens            │
│  plan                4,000 tokens            │
│  build              18,000 tokens            │
│  polish              6,000 tokens            │
│  review              8,000 tokens            │
│  verify             10,000 tokens            │
│  ────────────────────────────                │
│  Total:             58,000 tokens est.       │
│  Context budget:    ~200K remaining          │
│  Estimated fill:    29% of remaining         │
│                                              │
│  Models: 1 Opus, 3 Sonnet, 2 Haiku          │
│  Estimated cost: ~$0.42                      │
└──────────────────────────────────────────────┘
Proceed? [Y/n]
```

**Implementation:** Extend `workflow_cost.py` to:
1. Pull historical average tokens per skill from SQLite (`sum_skill_summary`)
2. Fall back to `estimated_tokens` in YAML if no history
3. Check current context budget from context-threshold bridge
4. Calculate fill percentage
5. Print cost table before execution

### Model Auto-Selection Based on History

Use SQLite skill summaries to auto-select model tier:

```python
# If skill historically succeeds >95% with Haiku → use Haiku
# If skill historically fails >20% with Haiku → upgrade to Sonnet
# If task involves architecture/complex analysis → Opus
```

**Implementation:** Add `model_selector.py` to `hooks/lib/` that queries `sum_skill_summary` and returns recommended model.

### Findings Summarizer (new Python script)

```
py hooks/lib/findings_summarizer.py <findings-file> [--format json|compact]
```

Takes raw audit findings (500-2000 words of prose) → outputs structured JSON (~100-200 words):
```json
{
  "total": 12,
  "critical": 2,
  "high": 3,
  "medium": 5,
  "low": 2,
  "findings": [
    {"severity": "critical", "file": "src/auth.ts:42", "title": "SQL injection", "fix": "use parameterized query"}
  ]
}
```

**Impact:** Every workflow node that passes findings to the next node saves ~70% tokens.

---

## Design: Python Context Efficiency Layer

### The Problem in Detail

Every time a subagent spawns (build mode, workflow node, review dispatch), it receives:
1. **SKILL.md** — 500-1800 words of instructions (read via Read tool = tokens consumed)
2. **Shared modules** — orchestration.md (800 words), quality.md, format.md
3. **Project context** — the agent explores files, reads configs, maps the repo structure
4. **Task-specific content** — plan text, findings from prior nodes, file contents

Items 1-3 are mostly identical across agents in the same session. Item 4 is often bloated prose when structured data would suffice. The current system has no mechanism to deduplicate or compress any of this.

### Script 1: `repo_context.py` — Generate Once, Reference Everywhere

```
py hooks/lib/repo_context.py [--project-root .] [--output .sessions/<date>/repo-context.json]
```

**Runs once per session** (or per workflow start). Produces a cached snapshot:

```json
{
  "tree": "src/\n  auth/\n    login.ts\n    middleware.ts\n  api/\n    routes.ts\n  ...",
  "stack": {
    "language": "typescript",
    "framework": "astro",
    "runtime": "cloudflare-workers",
    "db": "d1",
    "orm": "drizzle"
  },
  "entry_points": ["src/index.ts", "src/pages/index.astro"],
  "dependencies": {"prod": 12, "dev": 8, "heavy": ["@astrojs/cloudflare"]},
  "file_count": 47,
  "loc": 3200
}
```

**How agents use it:** Instead of each agent running Glob/Grep to orient itself, the workflow runner passes the cached JSON as inline context. ~200 words vs ~2000 words of exploration output.

**Cache invalidation:** Regenerate if git status shows file additions/deletions since last run. Modifications don't invalidate (structure unchanged).

### Script 2: `context_compiler.py` — Minimal Prompt Per Agent

```
py hooks/lib/context_compiler.py --skill=build --task=3 --project-root . [--repo-context .sessions/<date>/repo-context.json]
```

Takes a skill mode + task reference → outputs a **compiled prompt** containing ONLY what that specific agent needs:

```
Current behavior (what each agent loads):
  SKILL.md full text ........... ~1200 words
  orchestration.md .............. ~800 words
  quality.md .................... ~400 words
  gotchas.yml ................... ~200 words
  Project exploration ........... ~1500 words
  Task text ..................... ~300 words
  ─────────────────────────────────────────
  Total:                         ~4400 words

With context_compiler.py:
  Relevant SKILL.md sections .... ~300 words (skip examples, anti-patterns the agent doesn't need)
  Inline rules (from orchestration, quality) ~150 words (only rules relevant to this task type)
  Relevant gotchas .............. ~50 words (only gotchas for this mode)
  Repo context (cached JSON) .... ~200 words
  Task text ..................... ~300 words
  ─────────────────────────────────────────
  Total:                         ~1000 words (~77% reduction)
```

**How it works internally:**
1. Reads the SKILL.md for the requested mode
2. Parses sections by header — keeps "Steps", "Output", relevant "Anti-patterns"
3. Drops "Example Usage", "Template" boilerplate, "Trigger" (agent doesn't need routing info)
4. Reads gotchas.yml — includes only `avoid` items with severity >= high
5. From orchestration.md — extracts only the model selection table + response handling rules
6. Merges repo-context.json (if provided) instead of full project exploration
7. Outputs a single compiled markdown string ready to paste into an Agent prompt

**Key design constraint:** The compiled output must be a STATIC PREFIX that's identical for all agents of the same skill type in the same session. This enables Claude's automatic prompt caching (5-minute TTL). The task-specific content goes AFTER the static prefix as a dynamic suffix.

### Script 3: `prompt_assembler.py` — Cache-Optimized Prompt Building

```
py hooks/lib/prompt_assembler.py --template=implementer --static-context=<path> --task-text="<text>"
```

Builds prompts using the two-part structure from `orchestration.md`:

```
┌──────────────────────────────────────────────┐
│ STATIC PREFIX (identical across agents)       │
│  - Project context (from repo_context.py)     │
│  - Skill rules (from context_compiler.py)     │
│  - Output format specification                │
│  ═══════════════════════════════════════════  │
│ DYNAMIC SUFFIX (varies per agent)             │
│  - Task text                                  │
│  - Decisions so far                           │
│  - File contents (if needed, pasted inline)   │
└──────────────────────────────────────────────┘
```

**Why this matters for caching:** Claude's prompt cache has a 5-minute TTL. If you spawn 4 agents in a build wave and they all share the same static prefix, agents 2-4 get cache hits on the prefix. The `prompt_assembler` ensures the prefix is byte-identical.

**Templates available:**
- `implementer` — for build mode task execution
- `reviewer` — for spec compliance + code quality review
- `auditor` — for audit/scan skill agents
- `explorer` — for Haiku exploration subagents (minimal: repo context + question only)

### Script 4: `findings_summarizer.py` — Compress Inter-Node Data

Already specified above. Key addition: workflow nodes that produce findings should pipe output through this before passing to the next node:

```yaml
# In workflow YAML, nodes can declare output compression
nodes:
  - id: audit-deps
    command: "..."
    output_compress: findings  # tells workflow runner to pipe through findings_summarizer.py
```

The workflow engine (`workflow_engine.py`) would call findings_summarizer.py automatically when `output_compress: findings` is set, before resolving `{{audit-deps.output}}` templates for downstream nodes.

### Script 5: `session_cache.py` — In-Memory Session File Server

```
py hooks/lib/session_cache.py --session-dir .sessions/<date>/ --query <filename>
```

Problem: The `optimize.yaml` workflow has 8 nodes that each read from `.sessions/<date>/`. Each read = a Read tool call = tokens for the file content appearing in context. If 4 nodes read the same baseline file, that's 4x the tokens.

Solution: `session_cache.py` reads all session files once and serves them via stdout when queried. Workflow nodes call the script instead of using the Read tool:

```yaml
# Instead of: "Read .sessions/<date>/optimize-baseline.md"
# Node command says: "The baseline metrics are: {{session:optimize-baseline.md}}"
# Workflow engine resolves {{session:*}} by calling session_cache.py
```

**Implementation:** Add a `{{session:<filename>}}` template syntax to `workflow_engine.py`'s template resolver. When encountered, call `session_cache.py` which reads the file and returns contents. The content gets inlined into the agent prompt — one Read per file total, not per node.

### How the Scripts Chain Together

```
Session start (or workflow start):
  ┌─ repo_context.py ─────────────────────────────┐
  │  Scans project once → repo-context.json        │
  └────────────────────────┬───────────────────────┘
                           │
  For each workflow node:  │
  ┌─ context_compiler.py ──▼──────────────────────┐
  │  SKILL.md + repo-context → compiled rules      │
  └────────────────────────┬───────────────────────┘
                           │
  ┌─ prompt_assembler.py ──▼──────────────────────┐
  │  compiled rules + task text → full prompt       │
  │  (static prefix + dynamic suffix)              │
  └────────────────────────┬───────────────────────┘
                           │
  Agent executes with minimal prompt ◄─────────────┘
                           │
  ┌─ findings_summarizer.py ──────────────────────┐
  │  Agent output → compressed JSON for next node  │
  └────────────────────────┬───────────────────────┘
                           │
  ┌─ session_cache.py ─────▼──────────────────────┐
  │  Serves cached files to downstream nodes       │
  └────────────────────────────────────────────────┘
```

### Integration Points with Existing Code

| Existing file | Change needed |
|---|---|
| `workflow_engine.py` | Add `{{session:*}}` template resolution; call `session_cache.py` |
| `workflow_engine.py` | Add `output_compress` node property; call `findings_summarizer.py` after node completion |
| `workflow_state.py` | Call `repo_context.py` on `start` command; store path in workflow state |
| `skills/core/modes/build/SKILL.md` | Update subagent dispatch to use `prompt_assembler.py` instead of inline SKILL.md reads |
| `skills/core/orchestration.md` | Document the compiled prompt pattern; update implementer template |

---

## Design: Existing Workflow Optimizations

Beyond new scripts and workflows, the existing workflows have efficiency gains available:

### A. Model Tier Downgrades

| Workflow | Node | Current | Recommended | Rationale |
|---|---|---|---|---|
| idea-to-pr | plan | Opus | Sonnet | Spec already constrains plan space; Sonnet sufficient |
| idea-to-pr | think | Opus | Opus | Keep — architecture judgment needs Opus |
| fix-issue | review | Sonnet | Haiku | Quick check for small fixes; auto-escalate if complex |
| optimize | audit-code | Sonnet | Haiku | Pattern matching, not judgment; Haiku handles grep-style work |

### B. Parallel Node Regrouping

**project-audit.yaml** currently runs harden → secure → review sequentially with gates between each. These are independent audits — they can run in parallel:

```yaml
# Current: sequential with gates (3x serial time)
harden → [gate] → secure → [gate] → review → report

# Proposed: parallel audits, single gate before report
[harden, secure, review] (parallel) → [gate] → report
```

**Savings:** 2x faster execution, same total tokens but sessions finish sooner (less context drift).

### C. Short-Circuit Conditions for Workflow Nodes

Add `condition` checks that skip irrelevant work:

```yaml
# optimize.yaml — skip audit-infra if no Docker/Cloudflare/CI config
- id: audit-infra
  depends_on: [profile]
  condition: "{{profile.has_infra}} == true"  # set by profile node

# optimize.yaml — skip audit-queries if no ORM/SQL detected
- id: audit-queries
  depends_on: [profile]
  condition: "{{profile.has_data_layer}} == true"  # already partially done
```

**Savings:** Skip 2-3 nodes per workflow when they don't apply. Each skipped node saves ~4-8K tokens.

### D. Session File Deduplication

Multiple workflow nodes currently write separate findings files and the synthesize node reads all of them. With `session_cache.py`, the synthesize node gets pre-loaded content instead of doing 4-6 Read tool calls.

---

## Design: Dead Code Cleanup

| Item | Action |
|---|---|
| `hooks/lib/skill_metrics.py` | DELETE — duplicate of on-skill-metrics.py hook |
| `hooks/lib/telemetry.py` (Sentry) | KEEP but document as optional — not blocking anything |

---

## Design: on-skill-complete Hook

New hook that fires after a Skill tool completes:

```python
# packs/meta/hooks/on-skill-complete.py
# Trigger: PostToolUse on Skill tool
# 
# 1. Read the skill's chain_suggests metadata
# 2. Evaluate the condition (always, ui_build, findings_found, etc.)
# 3. If condition met, print suggestion:
#    "→ [polish] UI changes detected — run polish? (say 'polish' to continue)"
# 4. Log the suggestion to skill-usage.jsonl for tracking accept/reject rate
```

**Key constraint:** Advisory only — prints a suggestion, never auto-invokes. The user (Director) always decides.

---

## Success Criteria

- SC-001: Every skill has either a workflow home OR a chain-suggest entry (100% coverage)
- SC-002: Pre-run cost gate shows estimated tokens before workflow execution
- SC-003: Token savings of >=50% on subagent context loading (via context_compiler.py + prompt_assembler.py)
- SC-004: Token savings of >=70% on inter-node finding passing (via findings_summarizer.py)
- SC-005: Dead code (skill_metrics.py) removed
- SC-006: on-skill-complete hook prints next-step suggestions
- SC-007: 3 new Priority 1 workflows created and tested (audit-to-fix, ui-feature, client-deliverable)
- SC-008: Model auto-selection uses historical SQLite data for >=50% of workflow nodes
- SC-009: Polish skill integrated into UI build pipeline with auto-detection trigger
- SC-010: repo_context.py generates cached project snapshot; verified on 2+ real projects
- SC-011: Existing workflows (project-audit, optimize) updated with short-circuit conditions + parallel regrouping
- SC-012: workflow_engine.py supports `{{session:*}}` template syntax and `output_compress` property
- SC-013: prompt_assembler.py produces byte-identical static prefixes for agents of the same skill type (enabling prompt cache hits)

---

## Scope & Burden Assessment

### What this does NOT do (to keep scope manageable):
- Does NOT create workflows for every skill (career pack stays standalone — chain-suggest only)
- Does NOT change existing workflow BEHAVIOR (additive — no breaking changes to outputs)
- Does NOT add Sentry integration (keep telemetry.py as optional dead code)
- Does NOT refactor SKILL.md content (context_compiler extracts from existing files as-is)
- Does NOT require changes to how users invoke skills (transparent optimization layer)

### Burden controls:
- All 5 Python scripts are stdlib-only (no pip dependencies)
- Scripts fail gracefully — if context_compiler.py errors, fall back to current behavior (full SKILL.md read)
- Session cache is opt-in per workflow via `{{session:*}}` syntax — existing workflows unchanged unless updated
- Chain-suggest is advisory only — never auto-invokes skills, no new blocking hooks

### Estimated effort:
| Item | Effort | Session count |
|---|---|---|
| **Wave 1: Foundation (no dependencies)** | | |
| Dead code cleanup (delete skill_metrics.py) | Trivial | 0.1 |
| Chain-suggest metadata in all SKILL.md files (22 files) | Low | 0.5 |
| repo_context.py | Medium | 0.5 |
| findings_summarizer.py | Medium | 0.5 |
| model_selector.py | Low | 0.5 |
| **Wave 2: Integration (needs Wave 1)** | | |
| context_compiler.py (needs repo_context.py) | High | 1.0 |
| prompt_assembler.py (needs context_compiler.py) | Medium | 0.5 |
| session_cache.py | Low | 0.5 |
| on-skill-complete hook (needs chain-suggest metadata) | Medium | 0.5 |
| **Wave 3: Workflow Engine Updates (needs Wave 2)** | | |
| workflow_engine.py: `{{session:*}}` + `output_compress` | Medium | 0.5 |
| Pre-run cost gate (extend workflow_cost.py + model_selector) | Medium | 0.5 |
| Update build mode to use prompt_assembler | Medium | 0.5 |
| **Wave 4: New Workflows + Existing Optimizations** | | |
| audit-to-fix.yaml | Low | 0.5 |
| ui-feature.yaml | Low | 0.5 |
| client-deliverable.yaml | Medium | 0.5 |
| Optimize existing workflows (parallel regroup, short-circuit, model downgrades) | Medium | 0.5 |
| **Total** | | **~7 sessions** |

### Execution waves (dependency-ordered):

**Wave 1** (Sessions 1-2): Foundation scripts + metadata
- No dependencies on each other — can parallelize within sessions
- Delivers: repo_context.py, findings_summarizer.py, model_selector.py, chain-suggest in all SKILL.md files
- Immediately usable: findings_summarizer can be called manually, chain-suggest metadata is readable

**Wave 2** (Sessions 3-4): Core compilation layer
- Depends on Wave 1: context_compiler needs repo_context, prompt_assembler needs context_compiler
- Delivers: the full prompt compilation pipeline, session_cache, on-skill-complete hook
- Immediately usable: build mode can start using compiled prompts

**Wave 3** (Session 5): Workflow engine integration
- Depends on Wave 2: engine needs session_cache and findings_summarizer wired in
- Delivers: automated compression in workflow execution, pre-run cost gates
- Immediately usable: all existing workflows get cheaper to run

**Wave 4** (Sessions 6-7): New workflows + tune existing ones
- Depends on Wave 3: new workflows should use the efficiency layer from day one
- Delivers: audit-to-fix, ui-feature, client-deliverable, optimized existing workflows
- Immediately usable: full workflow coverage for all skill lifecycle patterns

---

## Next in Pipeline
→ `plan` (break into executable tasks across ~4 sessions)

Waiting for Director approval before plan.
