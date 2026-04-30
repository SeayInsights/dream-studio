# Implementation Plan: External Domain Intelligence
**Date**: 2026-04-29 | **Spec**: `.planning/specs/external-domain-intelligence/`  
**Goal**: Give dream-studio the ability to handle any domain — internal structure first, specialist knowledge on demand. Zero setup friction for end users.

---

## Scope Evaluation — dream-studio Principles Check

Before architecture: every original scope item evaluated against "enhance before importing, our structure wins, never adopt someone else's architecture."

### What changed and why

| Original item | Verdict | Reason |
|---|---|---|
| `skills/domains/external-registry.yml` | ❌ Eliminated | `ingest-log.yml` already IS the registry. Two SSOTs = drift. Extend the existing file instead. |
| `agent-eval-rubric.yml` | ✅ Kept, renamed | Rename to `eval-rubric.yml` — applies to all external sources, not just agents. Frame around dream-studio quality standards, not VoltAgent's. |
| `skills/external-agents/` directory | ❌ Wrong location | `skills/` is strictly the Skill tool layer. Claude Code agents belong in `.claude/agents/`. Ship as top-level `agents/` in repo; README install step copies to `~/.claude/agents/`. |
| New domain YAMLs (infra/mobile/data) | ✅ Unchanged | Follows existing `skills/domains/bi/`, `design/`, `devops/` pattern exactly. |
| Coach full dispatch mechanism | ⚠️ Simplified | Claude Code auto-invokes installed agents natively via description matching — no coach dispatch needed. Coach only handles the "agent not installed" gap: check ingest-log keywords, suggest install command. 5 lines, not a dispatch system. |
| `type: agent` workflow node | ✅ Kept, renamed | `agent:` field already exists in workflow nodes as persona hint. Rename to `type: specialist` to avoid collision. Resolves against ingest-log, dispatches via Task tool. |
| `studio-onboard.yaml` extension | ❌ Separate workflow | Studio-onboard = user environment setup. Domain ingest = knowledge synthesis. Different concerns. New `domain-ingest.yaml` workflow instead. Studio-onboard untouched. |
| New scheduling infrastructure | ⚠️ Extend existing | `on-pulse` already checks stale items. Add ingest-log `refresh_due` check there. New `domain-refresh.yaml` workflow for re-synthesis, triggered by schedule or manually. |
| install.sh | 📝 README only | No install.sh exists. One README section: copy `agents/` to `~/.claude/agents/`. |

### What VoltAgent architecture we are NOT adopting

- ❌ Numbered category directories (`01-core-development/`)
- ❌ `.claude-plugin` manifests per category
- ❌ `install-agents.sh` interactive installer
- ❌ Persona-first framing ("you are a senior X expert") in any dream-studio file
- ❌ Mirroring their catalog structure inside dream-studio

### What we ARE building (dream-studio native)

- Extending existing `ingest-log.yml` schema (SSOT we already own)
- New domain YAMLs in existing `skills/domains/` pattern
- Top-level `agents/` directory (native Claude Code pattern, not VoltAgent's)
- Evaluation rubric framed around dream-studio quality: gotchas-first, workflow-integrated, artifact-producing
- New workflow `domain-ingest.yaml` using existing workflow engine

---

## Architecture

### Layer model (unchanged — this integrates within it)

```
Layer 1: Python hooks (packs/)          — runtime events, pulse, scheduling
Layer 2: Skill guidance (skills/)       — SKILL.md workflows, domain YAMLs
Layer 3: Claude Code agents (agents/)   — specialist personas, NEW
```

Agents sit below skills. Skills orchestrate agents. Agents do not invoke skills.

### Two modes — kept clean and separate

**Mode A — Knowledge injection**: Domain YAML read as context by a skill. No agent runs. The skill just has richer domain knowledge for the problem at hand.

**Mode B — Specialist dispatch**: Agent file dispatched via Task tool in a workflow `type: specialist` node. The skill handles process/gates/artifacts. The agent provides domain expertise.

Same source material (agent file + domain YAML), different consumption paths. They are explicitly not the same thing.

### Registry = extended ingest-log (not a new file)

New fields added to existing `ingest-log.yml` schema for agent entries:

```yaml
# New fields for agent-type entries
keywords: [kubernetes, k8s, pod, helm, kubectl, cluster]   # for route-classify matching
persona_md_path: agents/kubernetes-expert.md               # local path in repo
quality_score: 8                                           # 1-10 from eval-rubric
sources_evaluated:
  - repo: VoltAgent/awesome-claude-code-subagents
    path: categories/03-infrastructure/kubernetes-expert.md
    score: 6
    contributed: [deployment_patterns, health_checks]
  - repo: company/production-repo
    path: .claude/agents/platform-engineer.md
    score: 9
    contributed: [gotchas, specific_commands, failure_modes]
enhancement_notes: "Added 4 production gotchas, version-specific k8s 1.28+ guidance"
```

### Evaluation rubric (dream-studio quality standards, not VoltAgent's)

Eight signals. Framed around what dream-studio demands, not what makes a good catalog persona:

1. `has_gotchas` — non-obvious failure modes documented
2. `has_anti_patterns` — explicit what-not-to-do
3. `has_specific_commands` — real CLI/tool commands, not concepts
4. `has_version_specifics` — current tool versions, not timeless prose
5. `battle_tested` — found in production repo, not just a catalog
6. `workflow_integrable` — produces verifiable artifacts (not just advice)
7. `has_concrete_examples` — shows real output
8. `maintained_recently` — last update < 90 days

Score: count of signals present (0-8). Threshold for bundling: ≥ 5. Threshold for domain YAML extraction: ≥ 4.

### Source evaluation strategy

Multi-source, ranked by quality signal density:

1. **GitHub code search** `path:.claude/agents extension:md` — battle-tested first
2. **VoltAgent/awesome-claude-code-subagents** — largest curated catalog
3. **VoltAgent/awesome-agent-skills** — broader collection, may have additional specialists
4. **MCP registry** (`modelcontextprotocol/servers`) — domain knowledge in tool implementations (different format, extract patterns not personas)

Stars are noted in ingest-log but never used as a quality criterion.

### domain-ingest workflow (new)

The evaluation pipeline for adding any new domain:

```
Phase 1 — Find sources
  → GitHub code search for domain keywords
  → VoltAgent catalog search
  → Return: list of candidate files with provenance

Phase 2 — Score and compare (dispatches analyze skill)
  → Score each candidate against eval-rubric
  → Compare: what does A have that B doesn't?
  → Identify synthesis opportunities

Phase 3 — Synthesize
  → Combine best content from all sources
  → Strip persona framing ("you are a senior X...")
  → Structure as: checklists, patterns, anti-patterns, gotchas
  → Output: domain YAML (skills/domains/) + enhanced persona MD (agents/)

Phase 4 — Register
  → Add entry to ingest-log.yml with full provenance
  → Set refresh_due = today + 90 days

Gate: Director reviews synthesis before commit
```

### Routing flow (post-implementation)

```
User intent → CLAUDE.md routing table
  ↓
Matches dream-studio skill trigger?
  YES → skill runs, loads relevant domain YAML as context if domain detected
  NO  → coach:route-classify
          ↓
        Match in ingest-log keywords?
          YES + agent installed in ~/.claude/agents/
            → Claude Code auto-invokes agent natively (no coach action needed)
          YES + agent NOT installed
            → coach suggests: "curl -s [remote_url] > ~/.claude/agents/[name].md"
          NO match
            → generic coach guidance + offer to run domain-ingest workflow

Multi-domain workflow?
  → workflow YAML uses type: specialist nodes
  → resolved via ingest-log by name
  → parallel or sequential per YAML config
  → skill gates/verifies output
```

---

## Technical Context

**Type**: dream-studio skill/domain-doc/workflow/hook  
**Language**: Markdown (skills), YAML (domains/registry), Python (hook extension)  
**Storage**: File system — `skills/domains/`, `agents/`, `workflows/`, `packs/`  
**Platform**: Claude Code plugin (cross-platform)  
**Constraints**: Zero end-user setup friction; no required GitHub API auth; works offline after install

## Priority Domains (synthesize in Phase 3)

| Domain | Why it matters | Sources to check |
|---|---|---|
| infra (k8s + terraform + devops) | Ubiquitous in production, zero dream-studio coverage today | VoltAgent + GitHub search (battle-tested infra repos) |
| mobile (iOS/Android/RN) | Dead end for mobile users today | VoltAgent + GitHub search |
| data pipelines (dbt/warehouse) | Common domain, light coverage | VoltAgent + GitHub search |
| research/analysis | Supplements think + analyze with web-research-first pattern | VoltAgent project-idea-validator (high value: anti-sycophancy built in) |
| accessibility + docs | Gaps in ship and polish | VoltAgent + GitHub search |

---

## Constitution check

- Extends ingest-log.yml (existing SSOT) ✅
- Follows skills/domains/ pattern ✅  
- Uses workflow engine (existing infrastructure) ✅
- Extends on-pulse (existing hook) ✅
- New agents/ directory follows Claude Code native pattern, not VoltAgent ✅
- No external dependencies required for core functionality ✅
- Persona framing stripped from all dream-studio files ✅
