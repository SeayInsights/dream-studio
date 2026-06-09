# Agent Architecture — Internal Reference

**Established:** 2026-06-03 (WO 18.9)
**Pattern origin:** WO 18.4.2b (accessibility-expert pilot)

> **Scope:** This document describes Dream Studio's internal agent architecture.
> It is NOT the Phase 20 public-facing AGENTS.md (the codex adapter projection at
> the repo root). That file is for external tool compatibility. This file is for
> internal architectural understanding and onboarding.

---

## What the Agent-as-Wrapper Pattern Is

Every domain-expert agent in Dream Studio is a **thin wrapper** (≤25 lines) that points
to a skill directory. The skill directory holds the actual content — patterns, gotchas,
commands, version notes — in a STRUCTURE.md v2.1 5-file layout.

```
canonical/agents/devops-engineer.md    ← thin wrapper (~20 lines)
canonical/skills/domains/modes/devops/ ← actual content
  SKILL.md                             ← patterns, anti-patterns, gotchas, commands
  metadata.yml                         ← skill metadata, tier, token tracking
  gotchas.yml                          ← structured gotchas with severity/category
  config.yml                           ← invocation type (subagent-target)
  changelog.md                         ← promotion history, content notes
```

The wrapper's entire job: tell the subagent where to find the SKILL.md. Nothing else.

---

## Why This Architecture Exists

### The problem before 18.9

Agents were bare markdown files (80-266 lines) with patterns, anti-patterns, gotchas,
commands, and version notes — but:
- No skill directory → no token attribution
- No metadata.yml → no tier graduation (JIT-pending → Standard → Stable)
- No JIT enrichment hooks → Phase 19 adaptive learning couldn't target them
- No structural consistency with the 11 quality skills

Functionally these were skills in agent clothing. The 18.4.2b pilot validated the fix.

### How subagent dispatch works

When the operator invokes `use devops-engineer to ...` via the Task tool:
1. Claude Code reads `~/.claude/agents/devops-engineer.md` (the wrapper)
2. Wrapper instructs: "Read SKILL.md from `~/.claude/skills/ds-domains/modes/devops/SKILL.md`"
3. Subagent reads the full SKILL.md as its operating instructions
4. Token count reflects the full skill content load (~3-5k tokens per skill)

The wrapper is in `agents/` because that's what the Task tool reads. The content is in
`skills/` because that's where the skill infrastructure lives. The two are linked by
the path in the wrapper.

---

## The 5-File Skill Minimum

Every promoted agent skill has exactly these files:

```
SKILL.md       — All content (verbatim from original agent, frontmatter removed)
metadata.yml   — Skill ID, pack, status, origin, quality metrics
gotchas.yml    — Structured gotchas with severity/category for tooling
config.yml     — Invocation type: subagent-target; fallback standard
changelog.md   — Promotion history; explicit notes on deferred decisions
```

### metadata.yml conventions for promoted agents

```yaml
status: jit-pending          # Promoted verbatim; enrich after first real usage
origin: promoted-from-agent  # Flag for tooling and Phase 19 signal routing
```

`jit-pending` means: we have the content, but haven't validated it in real usage yet.
Phase 19 will refine it based on actual invocations.

---

## How to Promote a New Agent

Pattern established by 18.4.2b. Follow these steps:

1. **Read the agent file** — understand its content structure
2. **Create the skill directory**: `canonical/skills/<pack>/modes/<mode>/`
3. **Write SKILL.md** — verbatim copy of agent content, frontmatter removed
4. **Write metadata.yml** — set `status: jit-pending`, `origin: promoted-from-agent`
5. **Extract gotchas.yml** — structure each gotcha with `id`, `title`, `description`, `severity`, `category`
6. **Write config.yml** — `invocation.type: subagent-target`, `wrapper_agent: <name>`, `dispatch_path: ~/.claude/agents/<name>.md`
7. **Write changelog.md** — document promotion date, any deferred decisions (like mode splits)
8. **Reduce agent file to wrapper** — ≤25 lines, path to SKILL.md, one fallback sentence
9. **Register in packs.yaml** — add mode to appropriate pack's modes list
10. **Validate via Task tool** — invoke the agent, confirm SKILL.md content loads (~token count matches content size)

---

## Boundary Documentation Conventions

When a skill shares conceptual space with another, document the boundary explicitly in:
- The skill's `metadata.yml` description field
- The skill's `changelog.md` first entry

### Worked example: devops / ops / terraform

These three skills cover adjacent infrastructure concerns. Each metadata.yml description
states the boundary explicitly:

**devops** — "Pre-runtime operational concerns: GitHub Actions CI/CD pipeline design,
OIDC cloud auth setup, release automation, Docker build optimization, branch protection,
and deployment gates."

**ops** — "Audits services for operational readiness: structured logging, health/metrics
endpoints, configuration discipline, graceful shutdown, retry/timeout patterns, and
deployment artifact quality (Dockerfile, k8s)."

**terraform** — "Terraform module design, remote state management... Scope boundary:
terraform covers IaC provisioning; devops covers CI/CD pipelines that deploy that
infrastructure; ops covers the runtime health of the resulting services."

Three distinct concerns: IaC provisioning → pipeline deployment → runtime health.
The 18.9.9 description collision check (Jaccard similarity) validated that all three
descriptions are sufficiently distinct (0 pairs at ≥ 0.50 similarity).

### Other documented boundaries

| Pair | Distinction |
|------|------------|
| mobile ↔ frontend-ux | mobile=native iOS/Android/RN/Flutter; frontend-ux=web/browser |
| data-engineering ↔ database | data-engineering=pipelines+warehouse; database=application schema integrity |
| research ↔ idea-validation | research=evidence gathering with source hierarchy; idea-validation=fatal flaw stress-testing |
| technical-writing ↔ (none) | No close neighbors in current skill set |

---

## Current Agent Inventory

| Agent file | Skill | Pack | Lines (pre-promotion) | Lines (post) |
|-----------|-------|------|----------------------|--------------|
| accessibility-expert.md | quality:accessibility | ds-quality | 89 | 18 |
| devops-engineer.md | domains:devops | ds-domains | 91 | 19 |
| kubernetes-expert.md | domains:kubernetes | ds-domains | 87 | 18 |
| research-analyst.md | analyze:research | ds-analyze | 91 | 16 |
| idea-validator.md | analyze:idea-validation | ds-analyze | 117 | 16 |
| technical-writer.md | domains:technical-writing | ds-domains | 121 | 16 |
| terraform-architect.md | domains:terraform | ds-domains | 108 | 16 |
| mobile-developer.md | domains:mobile | ds-domains | 158 | 18 |
| data-engineer.md | domains:data-engineering | ds-domains | 266 | 16 |

All content marked `status: jit-pending` — will be enriched by Phase 19 based on
real usage signals.

---

## Relationship to Other AGENTS.md Files

**This file** (`docs/architecture/AGENTS.md`) — Internal architecture documentation.
Explains the pattern, rationale, and conventions for Dream Studio contributors.

**`AGENTS.md` (repo root)** — Codex adapter projection. Used for external tool
compatibility (Codex, other AI coding tools). Not the same audience or purpose.

**Phase 20 public-facing AGENTS.md** — Per Decision 5, AGENTS.md will eventually
become the universal target format as CLAUDE.md becomes a Claude-Code-specific shim.
That work is Phase 20. This internal doc is a precursor, not the Phase 20 deliverable.
