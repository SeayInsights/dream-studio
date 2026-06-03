# Skill Directory Structure

Version: 2.1
Established: 2026-05-28 (WO 18.4.2b)

---

## Overview

Skills live under `canonical/skills/<pack>/modes/<mode>/`. Each skill is a directory containing a minimum of 5 files. Two sub-patterns exist depending on how the skill is invoked.

---

## Skill Sub-Patterns

| Pattern | Example | When to use |
|---|---|---|
| **Audit-mode skill** | `quality/security` | Skill invoked directly via `ds skill invoke` or as part of build/audit orchestration. Has rules to enforce, runs static + LLM passes, produces tiered findings reports. |
| **Subagent-target skill** | `quality/accessibility` | Skill invoked via Task tool subagent dispatch. Content-driven (patterns, checklists, examples); applied in context of the subagent's task. No separate audit/build modes. |

Both patterns share the same 5-file minimum. The audit-mode pattern extends it.

---

## File Reference

### Minimum (both patterns)

| File | Required | Purpose |
|---|---|---|
| `SKILL.md` | ✅ | Primary skill content: patterns, anti-patterns, checklists, procedures, tool commands |
| `metadata.yml` | ✅ | Identity, quality metrics, dependencies, discovery tags |
| `gotchas.yml` | ✅ | Structured operational gotchas with severity and category |
| `config.yml` | ✅ | Runtime configuration: invocation type, token budgets, graceful degradation flags |
| `changelog.md` | ✅ | Version history starting at v1.0.0 |

### Audit-mode extensions

| File | Purpose |
|---|---|
| `rules.yml` | Structured rule registry with severity, action.build_mode, and tool_command fields |
| `modes/audit/SKILL.md` | Audit-mode dispatch instructions and scope modes |
| `modes/build/SKILL.md` | Build-mode (pre-generation enforcement) instructions |
| `references/` | External reference materials (regulatory anchors, custom scanning rules) |
| `core-imports.md` | Shared module imports (e.g., git for --changed scope) |
| `smoke-test.md` | Manual smoke-test procedure for install validation |

---

## Agent-as-Thin-Wrapper Convention

**Established by WO 18.4.2b. Template for WO 18.9 (remaining 8 agents).**

### Rationale

Agents are subagent dispatch entrypoints, not content repositories. Skill content (patterns, checklists, gotchas) belongs in the skill directory where it can be versioned, enriched via JIT, and reused across invocation modes. The agent wrapper is a routing shim.

### Wrapper Format

```markdown
---
name: <agent-stem>
description: <one-line description of domain + capabilities>. (Tools: All tools)
---

You are a <domain> subagent. Your full set of patterns,
anti-patterns, gotchas, checklist, and tool commands is in:

  ~/.claude/skills/<pack>/modes/<mode>/SKILL.md

Read it completely before responding. Apply its <primary framework>
when classifying findings.

Universal principles that always apply:
- <highest-signal principle 1>
- <highest-signal principle 2>

If the skill file is unavailable, fall back to <safe default standard>.
```

### Required YAML fields

| Field | Required | Notes |
|---|---|---|
| `name` | ✅ | Must match filename stem; used by Task tool for dispatch |
| `description` | ✅ | Used for discovery UI; plain prose description (no `(Tools: All tools)` suffix — that is added by Claude Code display layer) |
| `model` | ❌ | Not used by dispatch; omit for consistency with existing agents |
| `tools` | ❌ | Not used by dispatch; omit for consistency with existing agents |

### Skill reference path

The wrapper body references the skill at its **installed path**: `~/.claude/skills/<pack>/modes/<mode>/SKILL.md`. This path is valid after `ds integrate install --scope user --execute`.

### Subagent dispatch verification (required for each agent promotion)

Before merging any agent wrapper reduction, verify all four:

1. Subagent fires via Task tool successfully (`subagent_type="<agent-stem>"`)
2. Subagent reads SKILL.md from the installed path
3. Subagent applies skill content (e.g., primary framework appears in output)
4. Subagent response shape matches pre-promotion behavior

If any fail: STOP. Document the failure mode. Do not merge.

### Session timing

New agent files added mid-session won't dispatch until the next Claude Code session start. Pre-existing agents being modified to wrappers (the 18.9 case) dispatch immediately after install — no session restart required.

### Agents promoted via this pattern

| Agent | Skill | WO | Date |
|---|---|---|---|
| `accessibility-expert` | `quality/accessibility` | 18.4.2b | 2026-05-28 |

*18.9 will add the remaining 8 agents to this table.*

---

## metadata.yml Schema

```yaml
# Required fields
name: <mode-name>
version: <semver>
pack: <pack-name>
created_at: <YYYY-MM-DD>
updated_at: <YYYY-MM-DD>

# Evolution tracking
origin: new | promoted-from-agent | refactored
parent_skills: []
generation: 0
created_by: human

# Quality & Health
status: jit-pending | active | deprecated
health: active | degraded | retired
tested_with_models: [sonnet]
tested_with_hosts: [claude-code]

# Performance metrics
quality_metrics:
  times_used: 0
  success_rate: null
  avg_token_usage: null
  avg_execution_time_seconds: null
  last_success: null
  last_failure: null

# Failure patterns
common_failures: []

# Dependencies
dependencies:
  core_modules: []
  tools_required: []
  tools_optional: []
  env_vars_required: []
  files_required: []
  calls_skills: []

# Compatibility
compatibility:
  min_context_window: <tokens>
  works_best_with: sonnet
  works_with: [sonnet, opus]
  platforms: [windows, macos, linux]

# Discovery
tags: []
category: <pack-name>
triggers: []
description: >
  <multi-line description>
```

### JIT Policy

New skills ship with `status: jit-pending`, all `quality_metrics` null. After first real usage, update `times_used`, `avg_token_usage`, and `last_success` via `ds-quality:learn`. Do not fabricate metrics.

---

## Directory Layout Example

```
canonical/skills/
  quality/
    modes/
      security/              ← audit-mode skill
        audit/
          SKILL.md
        build/
          SKILL.md
        changelog.md
        config.yml
        core-imports.md
        gotchas.yml
        metadata.yml
        rules.yml
        SKILL.md
        smoke-test.md
      accessibility/         ← subagent-target skill
        changelog.md
        config.yml
        gotchas.yml
        metadata.yml
        SKILL.md
```

---

## Agent-as-Wrapper Pattern (18.9 Full Rollout)

All domain-expert agents follow the **agent-as-wrapper** pattern established in WO 18.4.2b
and rolled out to all 9 agents in WO 18.9.

### Why

Prior to 18.9, agents were bare markdown files with patterns, gotchas, and commands -- but
no skill directory, no metadata, no tier, and no JIT enrichment hooks. Functionally they were
subagent-target skills in agent clothing. The promotion:

1. Moves content into the skill directory (token attribution, tier graduation, Phase 19 enrichment)
2. Reduces the agent file to a ~20-line wrapper
3. Closes the structural inconsistency -- every agent now participates in skill infrastructure

### Wrapper format (<=25 lines)

```markdown
---
name: <agent-name>
description: <one-line description>
---

You are a <domain> subagent. Your full [content] is in:

  ~/.claude/skills/<pack>/modes/<mode>/SKILL.md

Read it completely before responding.
[1-2 key principles or diagnostic shortcuts]
If the skill file is unavailable, fall back to [community standard].
```

### Corresponding skill directory

Each wrapper agent has a `canonical/skills/<pack>/modes/<mode>/` directory with the
5-file minimum (subagent-target pattern):

| File | Contents |
|------|---------|
| SKILL.md | Verbatim content from original agent (frontmatter removed) |
| metadata.yml | status: jit-pending, origin: promoted-from-agent |
| gotchas.yml | Structured gotchas extracted from agent content |
| config.yml | invocation.type: subagent-target |
| changelog.md | First entry: "Promoted from agent (WO 18.9)" |

### Current agent inventory (post-18.9)

| Agent | Skill |
|-------|-------|
| accessibility-expert (18.4.2b) | quality:accessibility |
| devops-engineer | domains:devops |
| kubernetes-expert | domains:kubernetes |
| research-analyst | analyze:research |
| idea-validator | analyze:idea-validation |
| technical-writer | domains:technical-writing |
| terraform-architect | domains:terraform |
| mobile-developer | domains:mobile |
| data-engineer | domains:data-engineering |

See `docs/architecture/AGENTS.md` for the full architecture rationale and boundary conventions.
