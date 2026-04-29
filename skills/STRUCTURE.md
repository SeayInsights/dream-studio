# Dream-Studio Skill Architecture Guide

This document defines the standardized structure for all dream-studio skills.

## Overview

As of 2026-04-28, dream-studio uses a structured skill framework that enables:
- **Evolution tracking** — Know where skills came from and how they've changed
- **Quality monitoring** — Track success rates, token usage, times used
- **Dependency visibility** — Understand which skills depend on core modules
- **Discoverability** — Auto-generated catalog makes skills searchable
- **Lessons learned** — Capture gotchas and best practices over time

## Skill Directory Structure

### Minimal Skill (all skills have this)
```
skill-name/
├── SKILL.md                    # Core orchestration logic
├── metadata.yml                # Evolution, quality, dependencies
├── gotchas.yml                 # Lessons learned (YAML-structured)
├── config.yml                  # Runtime configuration
└── changelog.md                # Version history
```

### Enhanced Skill (core skills have this)
```
skill-name/
├── SKILL.md
├── metadata.yml
├── gotchas.yml
├── config.yml
├── changelog.md
├── core-imports.md             # Module dependencies & impact analysis
├── smoke-test.md               # Quick validation
│
├── examples/                   # Realistic usage examples
│   ├── simple/
│   │   ├── input.md
│   │   └── output.md
│   └── complex/
│       ├── input.md
│       └── output.md
│
└── templates/                  # Prompt and output templates
    ├── agent-prompts/
    │   ├── implementer.md
    │   └── reviewer.md
    └── output-formats/
        ├── findings-report.md
        └── checkpoint.md
```

### Skills with Domain Logic
```
skill-name/
├── [all of above]
├── analysts/                   # Multi-perspective analysis patterns
│   ├── skeptic.md
│   ├── optimist.md
│   └── synthesizer.md
├── checklists/                 # Domain-specific checklists
│   └── security-checklist.md
└── rules/                      # Validation rules
    └── compliance-rules.yml
```

## File Purposes

### SKILL.md
**Purpose:** Core orchestration logic  
**Format:** Markdown with frontmatter  
**Required sections:**
- Frontmatter (name, description, pack)
- Imports (if uses core modules)
- Trigger (when to invoke)
- Process (step-by-step execution)

**Example:**
```markdown
---
name: build
description: Execute a plan with subagent-driven development
pack: core
---

## Imports
- core/git.md — commit formatting
- core/orchestration.md — subagent spawning

## Trigger
`build:`, `execute plan:`

## Process
Step 1: Load plan
Step 2: Execute tasks
...
```

### metadata.yml
**Purpose:** Evolution tracking, quality metrics, dependencies  
**Format:** YAML  
**Key fields:**
- `name`, `version`, `pack` — Basic info
- `origin`, `generation` — Evolution tracking
- `status`, `health` — Maturity indicators
- `quality_metrics` — Success rate, token usage, times used
- `dependencies` — Core modules, tools, env vars
- `tags`, `triggers` — Discovery

**Example:**
```yaml
name: build
version: 2.0.0
pack: core
status: tested
health: active
quality_metrics:
  times_used: 47
  success_rate: 0.94
dependencies:
  core_modules: [git, traceability, orchestration]
  tools_required: [git, gh]
triggers: ["build:", "execute plan:"]
```

### gotchas.yml
**Purpose:** Capture lessons learned  
**Format:** YAML with structured sections  
**Sections:**
- `avoid` — Things that went wrong (with root cause)
- `best_practices` — Patterns that work well
- `edge_cases` — How edge cases are handled
- `limitations` — Known constraints
- `deprecated` — Removed patterns

**Example:**
```yaml
avoid:
  - id: parallel-same-files
    severity: critical
    title: "Never dispatch parallel agents on same files"
    context: |
      Two agents modified config.ts simultaneously.
      Git merge conflict required manual resolution.
    fix: "Check task.files[] overlap before parallel dispatch"

best_practices:
  - id: pre-inline-context
    impact: high
    title: "Pre-inline context in subagent prompts"
    why: "Subagents don't waste tokens re-reading files"
    result:
      improvement: "30% token reduction"
```

### config.yml
**Purpose:** Runtime configuration and performance budgets  
**Format:** YAML  
**Key sections:**
- `thresholds` — When to checkpoint, trace, etc.
- `models` — Default model selection
- `behavior` — Feature flags
- `budgets` — Max tokens, time, context

**Example:**
```yaml
thresholds:
  max_tasks_before_checkpoint: 3

models:
  default: sonnet
  implementer: sonnet
  reviewer: sonnet

behavior:
  allow_parallel_execution: true

budgets:
  max_tokens: 150000
  max_context_percent: 80
```

### changelog.md
**Purpose:** Version history  
**Format:** Markdown (keep-a-changelog style)  
**Structure:**
```markdown
# Skill Name — Changelog

## [2.0.0] - 2026-04-28
### Added
- New feature

### Changed
- Updated behavior

### Fixed
- Bug fix
```

### core-imports.md
**Purpose:** Document core module dependencies and impact analysis  
**Format:** Markdown  
**Sections:**
- Imported Modules (list with usage)
- Impact Analysis (what breaks if module changes)
- Maintenance Notes

**Who needs it:** Skills that import core modules

### smoke-test.md
**Purpose:** Quick validation test  
**Format:** Markdown  
**Sections:**
- Setup (how to prepare test scenario)
- Run (command to invoke skill)
- Expected (what should happen)
- If It Fails (debugging checklist)

**Who has it:** Core skills (build, plan, review, verify, ship)

### examples/
**Purpose:** Realistic usage examples  
**Structure:**
- `simple/` — Basic use case
- `complex/` — Advanced use case with edge cases
- Each has `input.md` (user request + context) and `output.md` (skill output)

**Who has it:** Core skills

### templates/
**Purpose:** Reusable prompt and output templates  
**Structure:**
- `agent-prompts/` — Templates for spawning agents
- `output-formats/` — Templates for skill outputs

**Who has it:** Core skills

## Creating a New Skill

### Step 1: Use templates
```bash
cd C:\Users\Dannis Seay\builds\dream-studio\skills
mkdir new-skill
cd new-skill

# Copy templates
cp ../templates/metadata.yml.template metadata.yml
cp ../templates/gotchas.yml.template gotchas.yml
cp ../templates/config.yml.template config.yml
```

### Step 2: Edit metadata.yml
```yaml
name: new-skill
description: "Brief description"
pack: core  # or security, career, design, etc.
tags: [relevant, tags]
triggers: ["trigger:"]
```

### Step 3: Create SKILL.md
```markdown
---
name: new-skill
description: Brief description
pack: core
---

## Trigger
[When to invoke]

## Process
[Step-by-step execution]
```

### Step 4: Create changelog.md
```markdown
# New Skill — Changelog

## [1.0.0] - YYYY-MM-DD
### Added
- Initial implementation
```

### Step 5: Register in catalog
```bash
cd ..
py generate-catalog.py
```

## Updating an Existing Skill

### When you change a skill:

1. **Update SKILL.md** — Core logic changes
2. **Update metadata.yml** — If dependencies change
3. **Update gotchas.yml** — If you discovered a new pattern or issue
4. **Update config.yml** — If performance budgets change
5. **Add changelog entry** — Document the change
6. **Regenerate catalog** — `py generate-catalog.py`

### When you discover a gotcha:

Add to `gotchas.yml`:
```yaml
avoid:
  - id: descriptive-id
    severity: critical | high | medium | low
    discovered: YYYY-MM-DD
    title: "Short title"
    context: |
      What happened (detailed)
    fix: "How to prevent it"
```

### When quality metrics change:

Update `metadata.yml`:
```yaml
quality_metrics:
  times_used: 50  # increment
  success_rate: 0.96  # recalculate
  avg_token_usage: 14800  # update average
  last_success: 2026-04-28
```

Then regenerate catalog to see updated metrics.

## Best Practices

### 1. Keep SKILL.md focused
SKILL.md should be orchestration logic only. Extract:
- Prompts → `templates/agent-prompts/`
- Output formats → `templates/output-formats/`
- Examples → `examples/`

### 2. Reference core modules
Don't duplicate patterns. Reference core modules:
```markdown
## Imports
- core/git.md — commit formatting

## Process
Step 1: Commit changes
See: core/git.md — Commit referencing plan task
```

### 3. Update gotchas when you learn
Don't wait for a "lessons learned" session. Add to `gotchas.yml` immediately when you discover:
- A bug caused by a pattern
- A technique that significantly improved performance
- An edge case that required special handling

### 4. Version skills properly
- **1.x.x** — Foundational version (imports, basic structure)
- **2.x.x** — Major refactor or new capabilities
- **x.1.x** — Minor improvements, new examples
- **x.x.1** — Bug fixes, doc updates

### 5. Track metrics honestly
Don't inflate success rates. If a skill failed:
```yaml
quality_metrics:
  times_used: 48
  success_rate: 0.93  # 45/48 = 0.9375
  last_failure: 2026-04-28

common_failures:
  - pattern: "Context overflow in 10+ task builds"
    frequency: 3
    mitigation: "Use handoff after 8 tasks"
```

## Catalog Generation

The skill catalog is auto-generated from metadata.yml files.

### Generate catalog:
```bash
cd C:\Users\Dannis Seay\builds\dream-studio\skills
py generate-catalog.py
```

### Output:
`dream-studio-catalog.md` with:
- Skills by pack
- Quality metrics (success rates, token usage)
- Dependency graph
- Health dashboard

### Search catalog:
```bash
grep "security" dream-studio-catalog.md
grep "review" dream-studio-catalog.md
```

## Maintenance

### Monthly:
- Review `gotchas.yml` across all skills — promote patterns to core modules
- Check `quality_metrics` — identify underperforming skills
- Update deprecated skills in catalog

### Quarterly:
- Audit core module usage — consolidate duplicated patterns
- Review skill health status — deprecate unused skills
- Update architecture guide if patterns change

### When core modules change:
1. Check `core/REGISTRY.md` for affected skills
2. Update each skill's `core-imports.md`
3. Test affected skills
4. Update skill versions in `metadata.yml`
5. Regenerate catalog

## Questions?

- **"Where do I put X?"** — If it's reusable across skills, put in `core/`. If skill-specific, put in the skill directory.
- **"Should I create a new skill or extend an existing one?"** — New skill if it has a distinct trigger and purpose. Extend if it's a mode/variant of existing.
- **"When do I update metadata.yml vs SKILL.md?"** — SKILL.md for logic changes. metadata.yml for dependencies, metrics, tags.
- **"How often should I regenerate the catalog?"** — After any metadata.yml change, or batch update weekly.

---

## Skill Depth Policy

### JIT Enrichment — No Sprint

Skills are enriched **just-in-time**, not in advance. A skill that hasn't been used in a real build has no meaningful lessons to capture yet.

**Rule:** Enrich a skill (add examples, update gotchas.yml) the first time it is used for a real build. Not before.

**Why:** Premature enrichment produces generic examples and speculative gotchas. Real builds produce real failure modes.

**Ongoing depth builders:**
- `learn: harvest` — batch-scans session history for patterns, surfaces them for Director review
- `workflow: repo-ingest` — formalizes external knowledge intake into domain YAMLs
- `gotchas.yml` — updated immediately after any build that reveals a non-obvious failure

**Sprint enrichment is explicitly prohibited.** Do not schedule sessions to enrich thin skills across the board.

### Skill Tiers

| Tier | Skills | Depth |
|------|--------|-------|
| Enhanced | build, plan, review, verify, ship | Examples + templates + smoke tests + core-imports |
| Standard | analyze, comply, dast, game-dev, mitigate, netcompat, secure, security-dashboard, workflow | Rich SKILL.md (10K+ chars) |
| JIT-pending | mcp-build, dashboard-dev, saas-build, polish, career suite | Core patterns documented; enriches on first real use |

**JIT-pending skills are fully functional.** They have correct SKILL.md instructions and gotchas.yml. They just lack worked examples — which will be added from the first real build.

---

**Last updated:** 2026-04-29  
**Architecture version:** 2.1 (JIT enrichment policy + ARCHITECTURE.md layer separation)
